import threading

from gui_runner import GuiRunner


def run_in_thread(runner):
    thread = threading.Thread(target=runner.run)
    thread.start()
    return thread


def test_tasks_run_in_order_on_the_runner_thread_and_stop_ends_the_loop():
    runner = GuiRunner()
    seen = []
    runner.submit(lambda: seen.append(("a", threading.current_thread().name)))
    runner.submit(lambda: seen.append(("b", threading.current_thread().name)))
    runner.submit(runner.stop)

    thread = run_in_thread(runner)
    thread.join(timeout=5)

    assert [name for name, _ in seen] == ["a", "b"]
    assert {worker for _, worker in seen} == {thread.name}


def test_a_failing_task_does_not_stop_the_loop():
    runner = GuiRunner()
    seen = []

    def boom():
        raise RuntimeError("tk exploded")

    runner.submit(boom)
    runner.submit(lambda: seen.append("after"))
    runner.submit(runner.stop)
    run_in_thread(runner).join(timeout=5)

    assert seen == ["after"]


def test_submit_once_ignores_a_repeat_while_the_first_is_pending():
    runner = GuiRunner()
    seen = []
    runner.submit_once("settings", lambda: seen.append(1))
    runner.submit_once("settings", lambda: seen.append(2))  # second click while the first is still queued
    runner.submit(runner.stop)
    run_in_thread(runner).join(timeout=5)

    assert seen == [1]


def test_submit_once_allows_the_task_again_after_it_finished():
    runner = GuiRunner()
    seen = []
    first_done, second_done = threading.Event(), threading.Event()
    thread = run_in_thread(runner)

    runner.submit_once("settings", lambda: (seen.append(1), first_done.set()))
    assert first_done.wait(timeout=5)
    runner.submit_once("settings", lambda: (seen.append(2), second_done.set()))
    assert second_done.wait(timeout=5)

    runner.stop()
    thread.join(timeout=5)
    assert seen == [1, 2]


def test_inline_runner_executes_immediately():
    runner = GuiRunner(inline=True)
    seen = []
    runner.submit(lambda: seen.append("now"))
    assert seen == ["now"]
