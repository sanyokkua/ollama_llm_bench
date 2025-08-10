from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from ollama_llm_bench.core.interfaces import BenchmarkApplicationControllerApi
from ollama_llm_bench.ui.widgets.panels.control.new_run_widget import NewRunWidgetStartEvent
from ollama_llm_bench.ui.widgets.panels.control_panel import ControlPanel, ControlPanelModel
from ollama_llm_bench.ui.widgets.panels.results_panel import ResultsPanel, ResultsPanelModel

default_cp_model = ControlPanelModel(
    judge_models=[],
    models=[],
    runs=[],
)
default_res_model = ResultsPanelModel(
    runs=[],
    summary_data=[],
    detailed_data=[],
)


class CentralWidget(QWidget):
    def __init__(self, controller_api: BenchmarkApplicationControllerApi) -> None:
        super().__init__()
        self._api = controller_api
        self._control_panel = ControlPanel(default_cp_model)
        self._results_tab = ResultsPanel(default_res_model)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._control_panel)
        splitter.addWidget(self._results_tab)
        splitter.setSizes([100, 900])

        layout = QVBoxLayout()
        layout.addWidget(splitter)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self._control_panel.btn_new_run_stop_clicked.connect(self.on_control_panel_btn_new_run_stop_clicked)
        self._control_panel.btn_new_run_start_clicked.connect(self.on_control_panel_btn_new_run_start_clicked)
        self._control_panel.btn_new_run_refresh_clicked.connect(self.on_control_panel_btn_new_run_refresh_clicked)
        self._control_panel.btn_prev_run_refresh_clicked.connect(self.on_control_panel_btn_prev_run_refresh_clicked)
        self._control_panel.btn_prev_run_stop_clicked.connect(self.on_control_panel_btn_prev_run_stop_clicked)
        self._control_panel.btn_prev_run_start_clicked.connect(self.on_control_panel_btn_prev_run_start_clicked)
        self._results_tab.btn_export_csv_summary_clicked.connect(self.on_results_tab_btn_export_csv_summary_clicked)
        self._results_tab.btn_export_md_summary_clicked.connect(self.on_results_tab_btn_export_md_summary_clicked)
        self._results_tab.btn_export_csv_detailed_clicked.connect(self.on_results_tab_btn_export_csv_detailed_clicked)
        self._results_tab.btn_export_md_detailed_clicked.connect(self.on_results_tab_btn_export_md_detailed_clicked)
        self._results_tab.btn_delete_run_clicked.connect(self.on_results_tab_btn_delete_run_clicked)
        self._results_tab.dropdown_run_changed.connect(self.on_results_tab_dropdown_run_changed)

        self._api.subscribe_to_benchmark_status_events(self.set_benchmark_is_running)
        self._api.subscribe_to_benchmark_run_id_changed_events(self.update_results_tab_model)
        self._api.subscribe_to_benchmark_output_events(self.log_append_text)

        self.update_control_panel_model()
        self.update_results_tab_model()

    def on_control_panel_btn_new_run_stop_clicked(self):
        self._api.stop_benchmark()

    def on_control_panel_btn_new_run_start_clicked(self, event: NewRunWidgetStartEvent):
        print(event)
        judge_model, models = event.judge_model, event.models
        self._api.set_current_run_id(None)
        self._api.set_current_judge_model(judge_model)
        self._api.set_current_test_models(list(models))
        self._api.start_benchmark()

    def on_control_panel_btn_new_run_refresh_clicked(self):
        models = self._api.get_models_list()
        runs = self._api.get_runs_list()
        model_update = ControlPanelModel(
            judge_models=models,
            models=models,
            runs=runs,
        )
        self._control_panel.update_state(model_update)

    def on_control_panel_btn_prev_run_refresh_clicked(self):
        models = self._api.get_models_list()
        runs = self._api.get_runs_list()
        model_update = ControlPanelModel(
            judge_models=models,
            models=models,
            runs=runs,
        )
        self._control_panel.update_state(model_update)

    def on_control_panel_btn_prev_run_stop_clicked(self):
        self._api.stop_benchmark()

    def on_control_panel_btn_prev_run_start_clicked(self, run_id: int):
        print(run_id)
        self._api.set_current_run_id(run_id)
        self._api.set_current_judge_model('')
        self._api.set_current_test_models([])
        self._api.start_benchmark()

    def on_results_tab_btn_export_csv_summary_clicked(self):
        self._api.generate_summary_csv_report()

    def on_results_tab_btn_export_md_summary_clicked(self):
        self._api.generate_summary_markdown_report()

    def on_results_tab_btn_export_csv_detailed_clicked(self):
        self._api.generate_detailed_csv_report()

    def on_results_tab_btn_export_md_detailed_clicked(self):
        self._api.generate_detailed_markdown_report()

    def on_results_tab_btn_delete_run_clicked(self):
        self._api.delete_run()

    def on_results_tab_dropdown_run_changed(self, run_id: int):
        self._api.set_current_run_id(run_id)

    def update_control_panel_model(self) -> None:
        runs = self._api.get_runs_list()
        models = self._api.get_models_list()
        model = ControlPanelModel(
            judge_models=models,
            models=models,
            runs=runs,
        )
        self._control_panel.update_state(model)

    def update_results_tab_model(self, _=None) -> None:
        runs = self._api.get_runs_list()
        summary = self._api.get_summary_data()
        detailed = self._api.get_detailed_data()
        model = ResultsPanelModel(
            runs=runs,
            summary_data=summary,
            detailed_data=detailed,
        )
        self._results_tab.update_state(model)

    def set_benchmark_is_running(self, is_running: bool) -> None:
        self._control_panel.set_benchmark_is_running(is_running)
        self._results_tab.set_benchmark_is_running(is_running)

    def log_append_text(self, text: str):
        self._results_tab.log_append_text(text)
