## UI Implementation Plan

**Location**: `src/ollama_llm_bench/ui/`

---

### 1. App Context (`app_context.py`)

**Purpose**
Central DI container for UI; provides access to all backend interfaces.

**Class**:

```python
class AppContext:
    def __init__(
        self,
        benchmark_api: BenchmarkApi,
        llm_manager: LLMManagerApi,
        data_manager: DataManagerApi,
        dataset_loader: DataSetLoaderApi,
        prompt_api: PromptApi,
        task_manager: TaskManagerApi
    ):
        self._benchmark_api = benchmark_api
        self._llm_manager = llm_manager
        self._data_manager = data_manager
        self._dataset_loader = dataset_loader
        self._prompt_api = prompt_api
        self._task_manager = task_manager

    @property
    def benchmark_api(self) -> BenchmarkApi: …
    @property
    def llm_manager(self) -> LLMManagerApi: …
    # etc.
```

**Responsibilities**

* Expose each injected interface as a read-only property.
* Optionally, on init, pre-fetch the list of available models:

  ```python
  self.available_models = self._llm_manager.list_models()
  ```

---

### 2. Main Window (`main_window.py`)

**Class**:

```python
class MainWindow(QMainWindow):
    def __init__(self, app_context: AppContext):
        super().__init__()
        self.app_context = app_context
        self._subscription_tokens: list[int] = []
        self._setup_ui()
        self._wire_events()
```

#### 2.1. Layout Setup

1. **Central Widget**

   ```python
   central = QWidget()
   layout = QHBoxLayout(central)
   self.setCentralWidget(central)
   ```
2. **Left Column** (`control_panel_widget`)

   ```python
   self.control_panel_widget = QWidget()
   self.control_panel_layout = QVBoxLayout(self.control_panel_widget)
   layout.addWidget(self.control_panel_widget)
   ```
3. **Right Column** (`log_panel_widget`)

   ```python
   self.log_panel_widget = QWidget()
   self.log_panel_layout = QVBoxLayout(self.log_panel_widget)
   layout.addWidget(self.log_panel_widget)
   ```

#### 2.2. Control Panel Widgets

* **Judge Selector**

  ```python
  self.judge_label = QLabel("Judge Model:")
  self.judge_selector = QComboBox()
  self.judge_selector.addItems(self.app_context.available_models)
  ```

  *On change:*

  ```python
  self.judge_selector.currentTextChanged.connect(
      lambda name: self.app_context.benchmark_api.select_judge_model(name)
  )
  ```

* **Models to Benchmark**

  ```python
  self.models_label = QLabel("Models to Benchmark:")
  self.model_list = QListWidget()
  for model in self.app_context.available_models:
      item = QListWidgetItem(model)
      item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
      item.setCheckState(Qt.Unchecked)
      self.model_list.addItem(item)
  ```

  *On item change:*

  ```python
  self.model_list.itemChanged.connect(self._on_model_list_changed)
  def _on_model_list_changed(self, item):
      selected = [self.model_list.item(i).text()
                  for i in range(self.model_list.count())
                  if self.model_list.item(i).checkState() == Qt.Checked]
      self.app_context.benchmark_api.select_models(selected)
      self.start_button.setEnabled(bool(selected) and self.judge_selector.currentText())
  ```

* **Refresh Models Button**

  ```python
  self.refresh_button = QPushButton("Refresh Models")
  self.refresh_button.clicked.connect(self._refresh_models)
  ```

  *Implementation:*

  ```python
  def _refresh_models(self):
      lst = self.app_context.llm_manager.list_models()
      self.judge_selector.clear(); self.judge_selector.addItems(lst)
      self.model_list.clear()
      # repopulate model_list as above…
  ```

* **Start/Stop Buttons**

  ```python
  self.start_button = QPushButton("Start Benchmark")
  self.start_button.setEnabled(False)
  self.stop_button  = QPushButton("Stop Benchmark")
  self.stop_button.hide()
  ```

  *Start click:*

  ```python
  self.start_button.clicked.connect(self._on_start)
  def _on_start(self):
      self.log_view.clear()
      run_id = self.app_context.benchmark_api.start_benchmark()
      self._subscribe_all_events()
      self.start_button.hide()
      self.stop_button.show()
  ```

  *Stop click:*

  ```python
  self.stop_button.clicked.connect(self._on_stop)
  def _on_stop(self):
      self.app_context.benchmark_api.stop_benchmark()
      self._unsubscribe_all_events()
      self.stop_button.hide()
      self.start_button.show()
      self.status_label.setText("Stopped")
  ```

* **Progress Bar**

  ```python
  self.progress_bar = QProgressBar()
  self.progress_bar.setRange(0, 100)
  ```

* **Status Label**

  ```python
  self.status_label = QLabel("Idle")
  ```

#### 2.3. Log Panel

```python
self.log_view = QTextEdit()
self.log_view.setReadOnly(True)
self.log_panel_layout.addWidget(self.log_view)

def append_log(self, msg: str, error: bool=False):
    color = "red" if error else "black"
    self.log_view.append(f'<span style="color:{color}">{msg}</span>')
```

#### 2.4. Event Subscription & Handlers

```python
def _subscribe_all_events(self):
    api = self.app_context.benchmark_api
    self._subscription_tokens = [
        api.subscribe(BenchmarkEvent.STARTED, self._on_started),
        api.subscribe(BenchmarkEvent.STREAMING_RESULT, self._on_stream),
        api.subscribe(BenchmarkEvent.PROGRESS_CHANGED, self._on_progress),
        api.subscribe(BenchmarkEvent.ERROR, self._on_error),
        api.subscribe(BenchmarkEvent.COMPLETED, self._on_completed),
    ]

def _unsubscribe_all_events(self):
    for tok in self._subscription_tokens:
        self.app_context.benchmark_api.unsubscribe(tok)
    self._subscription_tokens.clear()
```

* **on\_started**

  ```python
  def _on_started(self, _):
      self.status_label.setText("Running…")
      self.append_log("Benchmark started")
  ```
* **on\_stream**

  ```python
  def _on_stream(self, token):
      self.append_log(token)
  ```
* **on\_progress**

  ```python
  def _on_progress(self, progress: BenchmarkProgress):
      pct = int(progress.percent_complete * 100)
      self.progress_bar.setValue(pct)
      self.status_label.setText(f"{progress.completed_tasks}/{progress.total_tasks}")
  ```
* **on\_error**

  ```python
  def _on_error(self, err: Exception):
      self.append_log(str(err), error=True)
      self.stop_button.hide()
      self.start_button.show()
  ```
* **on\_completed**

  ```python
  def _on_completed(self, _):
      self.append_log("Benchmark Completed")
      self.status_label.setText("Completed")
      self._unsubscribe_all_events()
      self.stop_button.hide()
      self.start_button.show()
  ```

---

### 3. Subwidgets & Helper Classes

* **`ModelSelectorWidget`**: label + combo or list logic, emits `selectionChanged`
* **`ControlPanel`**: aggregates judge selector, model list, buttons, progress bar, status label
* **`LogViewer`**: wraps `QTextEdit` with `log(msg, error=False)`
* **`AppContextProvider`** in `main.py`: constructs all implementations, builds `AppContext`

---

### 4. Wiring in `main.py`

```python
def main():
    # 1. Instantiate implementations under src/core/implementation
    benchmark_api    = BenchmarkService(...)
    llm_manager      = OllamaLLMManager(...)
    data_manager     = SqliteDataManager(...)
    dataset_loader   = YamlDataSetLoader(...)
    prompt_api       = SimplePromptApi(...)
    task_manager     = QtTaskManager(...)

    # 2. Build AppContext
    ctx = AppContext(
        benchmark_api, llm_manager, data_manager,
        dataset_loader, prompt_api, task_manager
    )

    # 3. Launch Qt UI
    app = QApplication(sys.argv)
    window = MainWindow(ctx)
    window.show()
    sys.exit(app.exec())
```

---

### 5. Edge-Case & Cleanup Considerations

1. **Disable “Start”** until at least one generation model **and** one judge model are selected.
2. **Prevent double-start** by immediately disabling the start button.
3. **Subscription cleanup** on both stop and window close to avoid stale callbacks.
4. **Stop event**

   * Optionally listen for a `STOPPED` event if your `BenchmarkApi` emits one.
5. **Phase distinction**

   * Update `status_label` to “Judging…” when entering the judgment phase.
6. **Error recovery**

   * After an error, allow the user to refresh models or restart a new run without restarting the app.

---