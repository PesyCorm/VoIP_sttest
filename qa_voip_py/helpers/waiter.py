import time

from typing import Callable


def try_wait(
        awaitable: Callable,
        check_result_eq_true: bool = False,
        wait_time: int = 10,
        frequency: int = 0.1,
        raise_after_time: bool = False,
        message_on_error: str = "Timeout error when trying to execute a function."
):
    """Ожидаем получения значения/результата выполнения от функции.
    :param awaitable: функция, которую пытаемся выполнить
    :param check_result_eq_true: получить bool значение от результата и проверить, что идентично True
    :param wait_time: время ожидания (сек)
    :param frequency: время периода опроса
    :param raise_after_time: выбросить исключение наружу при неудаче
    """
    assert wait_time > frequency
    st = time.time()
    while time.time() <= (st + wait_time):
        try:
            res = awaitable()
            if check_result_eq_true:
                assert bool(res), \
                    f"Полученный bool от результата выполнения функции - False: \n" \
                    f"Функция которую пытались выполнить: {awaitable}\n"
            return res
        except Exception as e:
            error = e
        time.sleep(frequency)
    else:
        logger.error(message_on_error)
        if raise_after_time:
            raise error  # noqa
        return False