from ollama_llm_bench.core.interfaces import DataApi


def get_tasks_tuple(data_api: DataApi) -> list[tuple[int, str]]:
    try:
        runs = data_api.retrieve_benchmark_runs()
        runs_list = [(r.run_id, r.timestamp) for r in runs]
        runs_list.sort(key=lambda x: x[1], reverse=True)
    except Exception as e:
        runs_list = []
    return runs_list
