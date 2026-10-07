# engine/pdf_report.py
from reportlab.lib.pagesizes import A4, letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus.flowables import Image
import os
from datetime import datetime
from db.models import TestRun, Measurement
from engine.guided_diagnostic import parse_guided_notes
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class PDFReportGenerator:
    """Gerador de relatórios PDF profissionais"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()
    
    def setup_custom_styles(self):
        """Configura estilos personalizados para o relatório"""
        # Estilo para título principal
        self.styles.add(ParagraphStyle(
            name='MainTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=1,  # Centralizado
            textColor=colors.HexColor('#2C3E50')
        ))
        
        # Estilo para subtítulo
        self.styles.add(ParagraphStyle(
            name='SubTitle',
            parent=self.styles['Heading2'],
            fontSize=12,
            spaceAfter=12,
            textColor=colors.HexColor('#34495E')
        ))
        
        # Estilo para cabeçalho de seção
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=6,
            spaceBefore=12,
            textColor=colors.HexColor('#2980B9'),
            borderBottom=1,
            borderColor=colors.HexColor('#3498DB'),
            borderPadding=5
        ))
        
        # Estilo para texto de destaque
        self.styles.add(ParagraphStyle(
            name='Highlight',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#27AE60'),
            backColor=colors.HexColor('#E8F6F3'),
            borderPadding=5,
            spaceAfter=6
        ))
    
    def generate_test_report(self, test_run: TestRun, image_path: Optional[str] = None, 
                           save_path: Optional[str] = None) -> str:
        """
        Gera relatório completo do teste
        
        Args:
            test_run: Execução do teste a ser relatada
            image_path: Caminho para imagem da placa (opcional)
            save_path: Caminho para salvar o PDF (opcional)
            
        Returns:
            Caminho do arquivo PDF gerado
        """
        if save_path is None:
            # Gera nome automático
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"relatorio_{test_run.board.serial_number}_{timestamp}.pdf"
            save_path = os.path.join("reports", filename)
        
        # Garante que o diretório existe
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        try:
            # Cria documento
            doc = SimpleDocTemplate(
                save_path,
                pagesize=A4,
                topMargin=1*cm,
                bottomMargin=1*cm,
                leftMargin=1.5*cm,
                rightMargin=1.5*cm,
                title=f"Relatório de Teste - {test_run.board.serial_number}"
            )
            
            # Elementos do relatório
            story = []
            
            # Cabeçalho
            story.extend(self._build_header(test_run))
            
            # Informações do teste
            story.extend(self._build_test_info(test_run))
            
            # Resultados
            story.extend(self._build_results_table(test_run))
            
            # Estatísticas
            story.extend(self._build_statistics(test_run))
            
            # Imagem da placa (se disponível)
            if image_path and os.path.exists(image_path):
                story.extend(self._build_image_section(image_path))
            
            # Rodapé
            story.extend(self._build_footer())
            
            # Gera PDF
            doc.build(story)
            logger.info(f"Relatório gerado com sucesso: {save_path}")
            
            return save_path
            
        except Exception as e:
            logger.error(f"Erro ao gerar relatório: {e}")
            raise
    
    def _build_header(self, test_run: TestRun):
        """Constrói cabeçalho do relatório"""
        elements = []
        
        # Título principal
        title = Paragraph("RELATÓRIO DE TESTE DE PLACA ELETRÔNICA", self.styles['MainTitle'])
        elements.append(title)
        elements.append(Spacer(1, 0.2*inch))
        
        # Informações da empresa
        company_info = [
            "Laboratório Técnico de Eletrônica",
            "Sistema Automático de Teste e Validação",
            f"Relatório gerado em: {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}"
        ]
        
        for info in company_info:
            p = Paragraph(info, self.styles['SubTitle'])
            elements.append(p)
        
        elements.append(Spacer(1, 0.3*inch))
        
        return elements
    
    def _build_test_info(self, test_run: TestRun):
        """Constrói seção de informações do teste"""
        elements = []
        
        # Cabeçalho da seção
        section_header = Paragraph("INFORMAÇÕES DO TESTE", self.styles['SectionHeader'])
        elements.append(section_header)
        
        # Dados do teste
        test_data = [
            ["Placa:", f"{test_run.board.name} ({test_run.board.serial_number})"],
            ["Modelo/Versão:", f"{test_run.board.model} v{test_run.board.version}"],
            ["Plano de Teste:", f"{test_run.plan.name} v{test_run.plan.version}"],
            ["Operador:", test_run.operator.username if test_run.operator else "N/A"],
            ["Data/Hora Início:", test_run.start_time.strftime('%d/%m/%Y %H:%M:%S')],
            ["Data/Hora Fim:", test_run.end_time.strftime('%d/%m/%Y %H:%M:%S') if test_run.end_time else "N/A"],
            ["Duração:", self._calculate_duration(test_run)],
            ["Status Final:", self._format_status(test_run.status)]
        ]
        
        # Cria tabela de informações
        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ECF0F1')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2C3E50')),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ])
        
        table = Table(test_data, colWidths=[2*inch, 4*inch])
        table.setStyle(table_style)
        elements.append(table)
        elements.append(Spacer(1, 0.2*inch))
        
        return elements
    
    def _build_results_table(self, test_run: TestRun):
        """Constrói tabela de resultados, incluindo o diagnóstico guiado."""
        elements = []
        section_header = Paragraph("RESULTADOS DAS MEDIÇÕES", self.styles['SectionHeader'])
        elements.append(section_header)

        guided = any(parse_guided_notes(m.notes) for m in test_run.measurements)
        if guided:
            header = ["Etapa", "Ponto", "Referência", "Medido", "Desvio", "Onda", "Status"]
            data = [header]
            for measurement in test_run.measurements:
                step = measurement.step
                point_ref = step.test_point.refdes if step.test_point else "N/A"
                info = parse_guided_notes(measurement.notes)
                if info:
                    expected = str(info.get("expected_summary") or "—")
                    measured = str(info.get("measured_summary") or "—")
                    deviations = []
                    for metric in (info.get("metrics") or {}).values():
                        pct = metric.get("deviation_pct")
                        if pct is not None:
                            deviations.append(f"{metric.get('label','')}: {pct:+.1f}%")
                    deviation_text = " | ".join(deviations) if deviations else "—"
                    sim = info.get("waveform_similarity_pct")
                    wave_text = f"{sim:.1f}%" if isinstance(sim, (int, float)) else "—"
                    status = str(info.get("status") or "—")
                else:
                    expected = f"{step.desired_value:.3f}" if step.desired_value is not None else "—"
                    measured = f"{measurement.value:.3f}" if measurement.value is not None else "—"
                    deviation_text = "—"
                    wave_text = "—"
                    status = "OK" if measurement.passed is True else ("FALHA" if measurement.passed is False else "N/A")
                data.append([
                    str(step.order_index),
                    point_ref,
                    expected,
                    measured,
                    deviation_text,
                    wave_text,
                    status,
                ])

            col_widths = [0.45*inch, 0.7*inch, 1.55*inch, 1.55*inch, 1.15*inch, 0.6*inch, 0.75*inch]
        else:
            header = ["Etapa", "Ponto", "Unidade", "Desejado", "Tolerância", "Medido", "Status"]
            data = [header]
            for measurement in test_run.measurements:
                step = measurement.step
                point_ref = step.test_point.refdes if step.test_point else "N/A"
                desired_str = f"{step.desired_value:.3f}" if step.desired_value is not None else "-"
                tolerance_str = f"±{step.tolerance:.3f}" if step.tolerance is not None else "-"
                measured_str = f"{measurement.value:.3f}" if measurement.value is not None else "N/A"
                status = "APROVADO" if measurement.passed is True else ("REPROVADO" if measurement.passed is False else "N/A")
                data.append([
                    step.description[:30] + "..." if len(step.description) > 30 else step.description,
                    point_ref,
                    step.unit or "-",
                    desired_str,
                    tolerance_str,
                    measured_str,
                    status,
                ])
            col_widths = [1.8*inch, 0.6*inch, 0.6*inch, 0.8*inch, 0.8*inch, 0.8*inch, 1*inch]

        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495E')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8F9FA')),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F0F3F4')]),
        ])
        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(table_style)
        elements.append(table)
        elements.append(Spacer(1, 0.2*inch))
        return elements

    def _build_statistics(self, test_run: TestRun):
        elements = []
        elements.append(Paragraph("ESTATÍSTICAS DO TESTE", self.styles['SectionHeader']))

        guided_infos = [parse_guided_notes(m.notes) for m in test_run.measurements]
        guided_infos = [x for x in guided_infos if x]
        if guided_infos:
            total = len(test_run.measurements)
            ok = sum(1 for x in guided_infos if x.get("status") == "OK")
            limit = sum(1 for x in guided_infos if x.get("status") == "LIMITE")
            fail = sum(1 for x in guided_infos if x.get("status") == "FALHA")
            unresolved = total - ok - limit - fail
            stats_data = [
                ["Total de etapas:", str(total)],
                ["Dentro da referência:", str(ok)],
                ["Próximo do limite:", str(limit)],
                ["Fora da tolerância:", str(fail)],
                ["Sem resultado / puladas:", str(unresolved)],
                ["Resultado final:", "REPROVADA" if fail else "APROVADA"],
            ]
        else:
            total = len(test_run.measurements)
            passed = sum(1 for m in test_run.measurements if m.passed is True)
            failed = sum(1 for m in test_run.measurements if m.passed is False)
            skipped = sum(1 for m in test_run.measurements if m.passed is None)
            success_rate = (passed / total * 100) if total else 0
            stats_data = [
                ["Total de Medições:", str(total)],
                ["Medições Aprovadas:", f"{passed} ({success_rate:.1f}%)"],
                ["Medições Reprovadas:", str(failed)],
                ["Medições Puladas/Não Realizadas:", str(skipped)],
                ["Resultado Final:", self._get_final_verdict(test_run)],
            ]

        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#E8F6F3')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#27AE60')),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
        ])
        table = Table(stats_data, colWidths=[2.5*inch, 3*inch])
        table.setStyle(table_style)
        elements.append(table)
        elements.append(Spacer(1, 0.2*inch))
        return elements

    def _build_image_section(self, image_path: str):
        """Constrói seção da imagem da placa"""
        elements = []
        
        section_header = Paragraph("IMAGEM DA PLACA COM PONTOS DE TESTE", self.styles['SectionHeader'])
        elements.append(section_header)
        
        try:
            # Adiciona imagem (redimensionada para caber na página)
            img = Image(image_path, width=5*inch, height=3*inch)
            img.hAlign = 'CENTER'
            elements.append(img)
            elements.append(Spacer(1, 0.1*inch))
            
            caption = Paragraph(
                "<i>Imagem da placa mostrando os pontos de teste marcados</i>",
                self.styles['Italic']
            )
            caption.hAlign = 'CENTER'
            elements.append(caption)
            
        except Exception as e:
            logger.warning(f"Erro ao adicionar imagem ao relatório: {e}")
            error_msg = Paragraph(
                "<i>[Erro ao carregar imagem da placa]</i>",
                self.styles['Italic']
            )
            elements.append(error_msg)
        
        elements.append(Spacer(1, 0.2*inch))
        return elements
    
    def _build_footer(self):
        """Constrói rodapé do relatório"""
        elements = []
        
        footer_text = [
            "---",
            f"Relatório gerado automaticamente pelo Sistema de Teste de Placas Eletrônicas",
            f"Versão 2.0 - {datetime.now().strftime('%Y')} - Laboratório Técnico"
        ]
        
        for text in footer_text:
            p = Paragraph(f"<font size=8 color='gray'>{text}</font>", self.styles['Normal'])
            p.hAlign = 'CENTER'
            elements.append(p)
        
        return elements
    
    def _calculate_duration(self, test_run: TestRun) -> str:
        """Calcula duração do teste"""
        if not test_run.end_time:
            return "N/A"
        
        duration = test_run.end_time - test_run.start_time
        total_seconds = int(duration.total_seconds())
        
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def _format_status(self, status: str) -> str:
        """Formata status para exibição"""
        status_map = {
            "completed": "✅ CONCLUÍDO",
            "failed": "❌ FALHOU", 
            "running": "🔄 EM EXECUÇÃO",
            "cancelled": "⏹️ CANCELADO",
            "error": "💥 ERRO"
        }
        return status_map.get(status, status.upper())
    
    def _get_final_verdict(self, test_run: TestRun) -> str:
        """Determina veredito final do teste"""
        if test_run.status == "completed":
            return "✅ PLACA APROVADA"
        elif test_run.status == "failed":
            return "❌ PLACA REPROVADA"
        else:
            return f"⚪ {test_run.status.upper()}"


# Funções de conveniência para compatibilidade
def export_test_report(test_run: TestRun, image_path: str, save_path: str) -> str:
    """
    Função de conveniência para exportar relatório
    """
    generator = PDFReportGenerator()
    return generator.generate_test_report(test_run, image_path, save_path)

def export_report_auto(test_run: TestRun, image_path: str) -> str:
    """
    Gera e salva relatório automaticamente
    """
    generator = PDFReportGenerator()
    return generator.generate_test_report(test_run, image_path)