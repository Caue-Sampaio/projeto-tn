        has_board = bool(self.selected_board)
        self.btn_edit_points.setEnabled(has_board)
        self.btn_view_points.setEnabled(has_board)
        self.btn_create_plan.setEnabled(has_board)

    def open_image_marker_edit(self):
        from ui.image_marker import ImageMarker
        if not self.selected_board:
            return
        if not self.selected_board.images:
            QMessageBox.warning(self, "Erro", "Nenhuma imagem cadastrada para esta placa.")
            return

        paths = [img.path for img in self.selected_board.images]
        choice, ok = QInputDialog.getItem(self, "Selecionar Imagem", "Escolha a imagem:", paths, 0, False)
        if ok and choice:
            self.marker = ImageMarker(self.session, self.selected_board, mode="edit", instruments=None)
            self.marker.load_image(choice)
            self.marker.show()

    def open_image_marker_view(self):
        from ui.image_marker import ImageMarker
        if not self.selected_board:
            return
        if not self.selected_board.images:
            QMessageBox.warning(self, "Erro", "Nenhuma imagem cadastrada para esta placa.")
            return

        paths = [img.path for img in self.selected_board.images]
        choice, ok = QInputDialog.getItem(self, "Selecionar Imagem", "Escolha a imagem:", paths, 0, False)
        if ok and choice:
            self.viewer = ImageMarker(self.session, self.selected_board, mode="view", instruments=None)
            self.viewer.load_image(choice)
            self.viewer.show()

    def open_plan_editor(self):
        from ui.plan_editor import PlanEditor
        if not self.selected_board:
            return
        self.editor = PlanEditor(self.session, self.selected_board)
        self.editor.show()
