# engine/runner.py
from sqlalchemy.orm import Session
from db.models import TestRun, TestStep, BoardUnit, User, Measurement
from datetime import datetime
import time
import logging
from typing import List, Tuple, Optional, Callable

logger = logging.getLogger(__name__)

class TestRunner:
    """Classe principal para execução de testes"""
    
    def __init__(self, session: Session):
        self.session = session
        self.is_running = False
        self.current_step = 0
        self.total_steps = 0
    
    def run_test(
        self,
        plan,
        board: BoardUnit,
        operator: User,
        instruments: dict,
        highlight_callback: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
        status_callback: Optional[Callable] = None
    ) -> Tuple[TestRun, List[Measurement]]:
        """
        Executa um plano de teste completo
        
        Args:
            plan: Plano de teste a ser executado
            board: Placa a ser testada
            operator: Operador responsável
            instruments: Dicionário com instrumentos disponíveis
            highlight_callback: Callback para destacar ponto atual na UI
            progress_callback: Callback para atualizar progresso
            status_callback: Callback para atualizar status
            
        Returns:
            Tuple com TestRun e lista de Measurements
        """
        self.is_running = True
        self.current_step = 0
        self.total_steps = len(plan.steps)
        
        try:
            # Cria registro da execução
            test_run = TestRun(
                board=board,
                operator=operator,
                plan=plan,
                start_time=datetime.now(),
                status="running"
            )
            self.session.add(test_run)
            self.session.flush()  # Para obter ID sem commit completo
            
            if status_callback:
                status_callback("Iniciando teste...")
            
            measurements = []
            
            # Ordena steps pelo order_index
            sorted_steps = sorted(plan.steps, key=lambda x: x.order_index)
            
            for step_index, step in enumerate(sorted_steps):
                if not self.is_running:
                    logger.info("Teste cancelado pelo usuário")
                    break
                    
                self.current_step = step_index + 1
                
                # Atualiza progresso
                if progress_callback:
                    progress_callback(self.current_step, self.total_steps, step.description)
                
                if status_callback:
                    status_callback(f"Executando: {step.description}")
                
                # Destaca ponto atual na UI
                if highlight_callback and step.test_point:
                    try:
                        highlight_callback(step)
                    except Exception as e:
                        logger.warning(f"Erro no highlight callback: {e}")
                
                # Executa medição
                measurement = self._execute_single_measurement(step, instruments, test_run)
                measurements.append(measurement)
                
                # Pequena pausa entre medições
                time.sleep(0.5)
            
            # Determina status final
            if self.is_running:
                all_passed = all(m.passed for m in measurements if m.passed is not None)
                test_run.status = "completed" if all_passed else "failed"
            else:
                test_run.status = "cancelled"
            
            test_run.end_time = datetime.now()
            
            # Commit final
            self.session.commit()
            
            logger.info(f"Teste finalizado: {test_run.status} - "
                       f"Placa: {board.serial_number} - "
                       f"Plano: {plan.name}")
            
            return test_run, measurements
            
        except Exception as e:
            logger.error(f"Erro durante execução do teste: {e}")
            if 'test_run' in locals():
                test_run.status = "error"
                test_run.end_time = datetime.now()
                self.session.commit()
            raise
        
        finally:
            self.is_running = False
    
    def _execute_single_measurement(
        self, 
        step: TestStep, 
        instruments: dict,
        test_run: TestRun
    ) -> Measurement:
        """
        Executa uma única medição
        """
        try:
            # Validações iniciais
            if not step.test_point:
                logger.warning(f"Step {step.description} sem ponto de teste associado")
                return self._create_skipped_measurement(step, test_run, "Sem ponto de teste")
            
            # Obtém instrumentos
            dmm = instruments.get("DMM")
            osc = instruments.get("OSC")
            
            measurement_data = {
                'value': None,
                'voltage': None,
                'current': None,
                'frequency': None,
                'waveform': None
            }
            
            # Executa medições baseadas no tipo
            if step.unit == 'V' and dmm:
                measurement_data['voltage'] = self._measure_voltage(dmm)
                measurement_data['value'] = measurement_data['voltage']
                
            elif step.unit == 'A' and dmm:
                measurement_data['current'] = self._measure_current(dmm)
                measurement_data['value'] = measurement_data['current']
                
            elif step.unit == 'Hz' and osc:
                measurement_data['frequency'] = self._measure_frequency(osc)
                measurement_data['value'] = measurement_data['frequency']
                
            elif step.unit in ['V', 'A'] and not dmm:
                logger.warning(f"DMM não disponível para medição de {step.unit}")
                return self._create_skipped_measurement(step, test_run, "DMM não disponível")
                
            elif step.unit == 'Hz' and not osc:
                logger.warning(f"Osciloscópio não disponível para medição de frequência")
                return self._create_skipped_measurement(step, test_run, "Osciloscópio não disponível")
            
            # Avalia resultado
            passed = self._evaluate_measurement(step, measurement_data)
            
            # Cria registro da medição
            measurement = Measurement(
                test_run=test_run,
                step=step,
                value=measurement_data['value'],
                unit=step.unit,
                passed=passed
            )
            
            self.session.add(measurement)
            self.session.flush()
            
            logger.info(f"Medição concluída: {step.description} - "
                       f"Valor: {measurement_data['value']} - "
                       f"Resultado: {'Aprovado' if passed else 'Reprovado'}")
            
            return measurement
            
        except Exception as e:
            logger.error(f"Erro na medição {step.description}: {e}")
            return self._create_error_measurement(step, test_run, str(e))
    
    def _measure_voltage(self, dmm) -> Optional[float]:
        """Mede tensão com DMM"""
        try:
            return dmm.measure_voltage()
        except Exception as e:
            logger.error(f"Erro na medição de tensão: {e}")
            return None
    
    def _measure_current(self, dmm) -> Optional[float]:
        """Mede corrente com DMM"""
        try:
            return dmm.measure_current()
        except Exception as e:
            logger.error(f"Erro na medição de corrente: {e}")
            return None
    
    def _measure_frequency(self, osc) -> Optional[float]:
        """Mede frequência com osciloscópio"""
        try:
            return osc.measure_frequency()
        except Exception as e:
            logger.error(f"Erro na medição de frequência: {e}")
            return None
    
    def _evaluate_measurement(self, step: TestStep, measurement_data: dict) -> bool:
        """
        Avalia se a medição está dentro dos limites especificados
        """
        measured_value = measurement_data['value']
        
        # Se não há valor medido, falha
        if measured_value is None:
            return False
        
        # Se não há valor desejado ou tolerância, considera aprovado
        if step.desired_value is None or step.tolerance is None:
            return True
        
        # Calcula limites
        lower_limit = step.desired_value - step.tolerance
        upper_limit = step.desired_value + step.tolerance
        
        # Verifica se está dentro dos limites
        is_within_limits = lower_limit <= measured_value <= upper_limit
        
        return is_within_limits
    
    def _create_skipped_measurement(self, step: TestStep, test_run: TestRun, reason: str) -> Measurement:
        """Cria uma medição pulada"""
        measurement = Measurement(
            test_run=test_run,
            step=step,
            value=None,
            unit=step.unit,
            passed=None,
            notes=f"Pulado: {reason}"
        )
        self.session.add(measurement)
        return measurement
    
    def _create_error_measurement(self, step: TestStep, test_run: TestRun, error: str) -> Measurement:
        """Cria uma medição com erro"""
        measurement = Measurement(
            test_run=test_run,
            step=step,
            value=None,
            unit=step.unit,
            passed=False,
            notes=f"Erro: {error}"
        )
        self.session.add(measurement)
        return measurement
    
    def cancel_test(self):
        """Cancela a execução do teste em andamento"""
        self.is_running = False
        logger.info("Teste cancelado pelo usuário")
    
    def get_progress(self) -> Tuple[int, int]:
        """Retorna progresso atual"""
        return self.current_step, self.total_steps


# Função de conveniência para compatibilidade
def run_test(
    session: Session,
    plan,
    board: BoardUnit,
    operator: User,
    instruments: dict,
    highlight_callback: Optional[Callable] = None,
    progress_callback: Optional[Callable] = None
) -> Tuple[TestRun, List[Measurement]]:
    """
    Função de conveniência para execução de teste
    """
    runner = TestRunner(session)
    return runner.run_test(plan, board, operator, instruments, highlight_callback, progress_callback)