import json
import os
import datetime as dt
from typing import Optional, Tuple


def load_settings(settings_filename: str = 'settings.json') -> Tuple[str, str, str, str, str, str, Optional[str]]:
    """
    Загружает настройки из JSON-файла.

    Parameters
    ----------
    settings_filename : str
        Имя файла с настройками. По умолчанию 'settings.json'.

    Returns
    -------
    Tuple[str, str, str, str, str, str, Optional[str]]
        Кортеж с настройками: (username, password, root_url, client_id, client_secret, auth_server, proxy_server).
        proxy_server возвращает None, если ключ отсутствует в файле.
    """
    if settings_filename is None:
        settings_filename = 'settings.json'

    with open(settings_filename) as datafile:
        jd = json.load(datafile)
        proxy_server = jd.get('proxy_server')
        return (
            jd['username'],
            jd['passw'],
            jd['root_url'],
            jd['client_id'],
            jd['client_secret'],
            jd['auth_server'],
            proxy_server
        )



def get_excel_filename(task_name: str, export_path: str = '../excel', add_date: bool = True) -> str:
    """
    Формирует путь к Excel-файлу для отчета с опциональной датой в имени.

    Parameters
    ----------
    task_name : str
        Название отчета/задания (без расширения).
    export_path : str
        Путь к директории для сохранения. По умолчанию '../excel'.
    add_date : bool
        Добавить текущую дату и время к имени файла. По умолчанию True.

    Returns
    -------
    str
        Полный путь к файлу вида 'task_name-YYYYMMDD_HHMMSS.xlsx'.
    """
    if not os.path.exists(export_path):
        os.makedirs(export_path, exist_ok=True)
    
    fname = task_name
    if add_date:
        fname += '-' + dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    fname += '.xlsx'
    
    return os.path.join(export_path, fname)
