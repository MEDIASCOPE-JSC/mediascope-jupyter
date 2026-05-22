#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import requests
import json
import os

import csv
import pandas as pd
import numpy as np
import zipfile
    
import datetime as dt
from datetime import date
from datetime import datetime
from datetime import timedelta
import glob
import plotly.express as px
from typing import Union

from pathlib import Path

from dateutil.relativedelta import relativedelta
import re


# In[ ]:




class FileApi:
    def create_url(self, filetype: str = '', period: str = 'list', method: str = 'list', payload_agency: str = '') -> str:
        """
        Формирует URL для API Mediascope на основе параметров.

        Параметры:
            filetype: Тип файла ('category_dict' - словарь категорий, 'brand_dict' - словарь брендов, 
                                 'socdem_dict' - словарь соц.-дема, 'activity' - активность)
            period: Период для фильтрации файла с активностью и словаря соц.-дема
            method: Метод API ('list' - для получения списка файлов, 'download' - для скачивания)

        """
        # Неизменяемая часть URL
        url_base = 'https://api.mediascope.net/file-delivery/api/v1/'
        # Проект
        project = 'projectName=share_of_search'
        agency = payload_agency

        # Метод получения списка определенных файлов или всего списка файлов: Метод list
        if method == 'list':
            # В зависимости от типа файла, по умолчанию - все файлы
            if filetype == 'cat_dict' or filetype == 'brand_dict':  # для просмотра словарей
                return f'{url_base}list?{project}&filterText={agency}/{filetype}/**'
            elif (filetype=='activity' or filetype=='socdem_dict') and period:  # для просмотра активности и соц.-дема с фильтром по периоду
                return f'{url_base}list?{project}&filterText={agency}/{filetype}/month={period[0]}/**'
            elif (filetype=='activity' or filetype=='socdem_dict'):  # для просмотра активности и соц.-дема за весь период
                return f'{url_base}list?{project}&filterText={agency}/{filetype}/**'
            else:  # для просмотра всех файлов
                return f'{url_base}list?{project}&filterText={agency}/**'

        # Метод скачивания файлов: download
        elif method == 'download':
            # В зависимости от типа файла, по умолчанию - все файлы
            if filetype == 'cat_dict' or filetype == 'brand_dict':
                return f'{url_base}downloadZip?{project}&files={agency}/{filetype}/*.csv'
            elif (filetype=='activity' or filetype=='socdem_dict') and period:  # для скачивания активности и соц.-дема с фильтром по периоду
                return f'{url_base}downloadZip?{project}&files={agency}/{filetype}/month={period[0]}/**'
            elif (filetype=='activity' or filetype=='socdem_dict'):  # для скачивания активности и соц.-дема за весь период
                return f'{url_base}downloadZip?{project}&files={agency}/{filetype}/**'
            else:  # для скачивания всех файлов
                return f'{url_base}downloadZip?{project}&files={agency}/**'
        else:
            raise ValueError(f"Unknown method: {method}")
        
    
    
    # функция для работы с File API
    def File_Api_Mediascope(self, filetype: str = '', period: str = '', method: str = 'list', token: str = '', payload_agency: str = ''):
        """
        Функция
            - получает токен
            - выполняет запросы к API для получения списка файлов (метод list) или скачивания архива с файлами (метод download).

        Параметры:
            filetype: Тип файла ('category_dict' - словарь категорий, 'brand_dict' - словарь брендов,
                                 'socdem_dict' - словарь соц.-дема, 'activity' - активность)
            period: Период для фильтрации файла с активностью и словаря соц.-дема
            method: Метод API ('list' - для получения списка файлов, 'download' - для скачивания)
            token: Токен для авторизации
        """
        
        token, payload_agency = FileApi().get_token_deliv()
        # Формирование заголовков для авторизации   
        headers = {
            'Authorization': f'Bearer {token}',
        }

        # Получаем URL с помощью функции create_url
        url = self.create_url(filetype=filetype, period=period, method=method, payload_agency=payload_agency)
        
        # Дата для названия файла
        time_now = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Для проверки даты при download activity и socdem_dict
        date_pattern = r'^\d{4}-\d{2}-01$'
        
        # Выполнение GET запроса, ответ от сервера сохраняем в response
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            if method == 'list':  # для метода list
                list_response = response.json()  # если запрос успешен, возвращаются данные в формате json

                files_info = [
                    (', '.join(file_info.get('file', '').split('/')[:3] if len(file_info.get('file').split('/')) > 3
                     else file_info.get('file', '').split('/')[:2]),  # выводится только значимая часть названия
                     file_info.get('lastUpdatedDate', '').split('T')[0])  # и дата обновления
                    for file_info in list_response if file_info.get('file')
                ]

                files_info.sort(key=lambda x: x[0], reverse=False)  # сортировка по названию файла
                
                for file_name, file_update in files_info:
                    print(f"File_name: {file_name}, Update: {file_update}")  # вывод списка файлов с указанием даты обновления

            elif method == 'download':
                if period and (filetype=='activity' or filetype=='socdem_dict'):
                    if not isinstance(period, list) and period is not None or not re.match(date_pattern, period[0]):
                        print("Значение 'period' должно быть в формате: ['YYYY-MM-01']")
                        return None
                    else:
                        period = period[0].replace('[', '').replace(']', '')
                        zip_filename = f'{filetype}_{period}-{time_now}.zip'
                elif period is None and (filetype=='activity' or filetype=='socdem_dict'):
                    zip_filename = f'{filetype}.zip'
                elif filetype == 'cat_dict' or filetype == 'brand_dict':
                    zip_filename = f'{filetype}-{time_now}.zip'
                elif filetype is None and period:
                    zip_filename = f'all_filetype-{time_now}.zip'
                else:
                    print('Задание сформировано некорректно.')
                    return None
                with open(zip_filename, 'wb') as file:
                    file.write(response.content)  # если запрос успешен, записать файл в архив
                return zip_filename
        else:
            if response.status_code == 401:
                print(f'Ошибка: {response.status_code}. Проблема с аутентификацией. Проверьте username, password в keys_file_api.txt')
            elif response.status_code == 400:
                print(f'Ошибка: {response.status_code}. Синтаксическая ошибка.\n\nВозможные ошибки:\n1. Неправильно указан период (или данных за этот период нет в вашей поставке)\n\nЕсли ошибка остается, напишите нам')
            elif response.status_code == 403:
                print(f'Ошибка: {response.status_code}. Что-то не так с правами доступа. Пишите нам')
            elif response.status_code == 404:
                print(f'Ошибка: {response.status_code}. Запрашиваемые данные не найдены. Пишите нам')
            else:
                print(f'Ошибка: {response.status_code}')

            return None
        
        
    def get_token_deliv(self):
        
        """
        Получает токен для работы с fileapi
        """
        # URL, необходимый для получения токена
        url_token = "https://auth.mediascope.net/auth/realms/mediascope/protocol/openid-connect/token"
        
        #Данные для аутентификации.Ключи и значения прописаны в txt 
        payload = {}
        empty_fields = []
        extra_space = []
        with open ('keys_file_api.txt', 'r', encoding='utf-8') as f:
            for line in f:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    # проверяем пробелы
                    if ' ' in line:
                        extra_space.append(key)
                        print(f'В файле keys_file_api.txt в строке "{key}" лишний пробел')
                    if not value:
                        empty_fields.append(key)
                        print(f'В файле keys_file_api.txt заполните поле "{key}"')
                    payload[key]=value
        
        # если есть синтаксические ошибки в txt файле
        if empty_fields or extra_space:
            print('Внесите изменения в "keys_file_api.txt"')
            error_found = True
        
        # Отправка POST-запроса для получения токена
        response_token = requests.post(url_token, data=payload)

        # Проверка, что запрос прошел успешно
        if response_token.status_code == 200:
            # Парсим полученный JSON с токеном
            token = response_token.json().get('access_token')#если запрос успешен, получен токен
            #print("Токен получен")
            return token, payload['agency']
        else:
            return False, False
    
    
    
    def open_zip(self, archives: list = None, periods: list = None):
        """
        Открывает несколько ZIP-архивов и извлекает CSV файлы

        """
        if archives is None:
            archives = []

        all_data = {}

        # Сортируем архивы по типу и дате
        cat_archives = []
        brand_archives = []
        activity_archives = []
        socdem_archives = []

        for archive in archives:
            if not archive.lower().endswith('.zip'):
                continue

            archive_name = os.path.basename(archive).lower().replace('.zip', '')

            if archive_name.startswith('cat_dict-'):
                cat_archives.append(archive)
            elif archive_name.startswith('brand_dict-'):
                brand_archives.append(archive)
            elif archive_name.startswith('activity'):
                activity_archives.append(archive)
            elif archive_name.startswith('socdem_dict'):
                socdem_archives.append(archive)

        # Берем самый свежий cat_dict (последний после сортировки)
        if cat_archives:
            cat_archives.sort()  # Сортировка по алфавиту = по дате
            latest_cat = cat_archives[-1]
            
            with zipfile.ZipFile(latest_cat, 'r') as zip_ref:
                for filename in zip_ref.namelist():
                    if filename.lower().endswith('.csv'):
                        with zip_ref.open(filename) as file:
                            df = pd.read_csv(file, low_memory=False, encoding='cp1251')
                            all_data['cat_dict'] = df
                        break

        # Берем самый свежий brand_dict
        if brand_archives:
            brand_archives.sort()
            latest_brand = brand_archives[-1]

            with zipfile.ZipFile(latest_brand, 'r') as zip_ref:
                for filename in zip_ref.namelist():
                    if filename.lower().endswith('.csv'):
                        with zip_ref.open(filename) as file:
                            df = pd.read_csv(file, low_memory=False, encoding='cp1251')
                            all_data['brand_dict'] = df
                        break

        # Обрабатываем activity архивы
        for archive in activity_archives:
            with zipfile.ZipFile(archive, 'r') as zip_ref:
                for filename in zip_ref.namelist():
                    if filename.lower().endswith('.csv'):
                        file_basename = os.path.basename(filename).lower().replace('.csv', '')

                        if periods:
                            # Извлекаем период из имени
                            if 'activity_' in file_basename:
                                file_period = file_basename.replace('activity_', '')
                            else:
                                file_period = file_basename.replace('activity', '')

                            file_period = file_period.strip("[]'\"")

                            if file_period in periods and file_basename not in all_data:
                                with zip_ref.open(filename) as file:
                                    df = pd.read_csv(file, low_memory=False, encoding='cp1251')
                                    all_data[file_basename] = df
                        else:
                            if file_basename not in all_data:
                                with zip_ref.open(filename) as file:
                                    df = pd.read_csv(file, low_memory=False, encoding='cp1251')
                                    all_data[file_basename] = df
        # Обрабатываем соц.-дем архивы
        for archive in socdem_archives:
            with zipfile.ZipFile(archive, 'r') as zip_ref:
                for filename in zip_ref.namelist():
                    if filename.lower().endswith('.csv'):
                        file_basename = os.path.basename(filename).lower().replace('.csv', '')

                        if periods:
                            # Извлекаем период из имени
                            if 'socdem_dict_' in file_basename:
                                file_period = file_basename.replace('socdem_dict_', '')
                            else:
                                file_period = file_basename.replace('socdem_dict', '')

                            file_period = file_period.strip("[]'\"")

                            if file_period in periods and file_basename not in all_data:
                                with zip_ref.open(filename) as file:
                                    df = pd.read_csv(file, low_memory=False, encoding='cp1251')
                                    all_data[file_basename] = df
                        else:
                            if file_basename not in all_data:
                                with zip_ref.open(filename) as file:
                                    df = pd.read_csv(file, low_memory=False, encoding='cp1251')
                                    all_data[file_basename] = df
        return all_data
    
    
    def create_pdDF(self, period: list = None, note: str = None, 
                          category_filter: Union[str, list] = None, 
                          flag_filter: bool = None, 
                          demo_filter: str = None, 
                          brand_filter: list = None,
                            brand_flag: bool = None):
        """
        Создает pandas.DataFrame из архивов с файлами в директории и проверяет указанные фильтры

        """
        current_dir = Path.cwd()

        # Ищем файлы в директории
        archive = []
        patterns = ['cat_dict*.zip', 'brand_dict*.zip', 'socdem_dict*.zip', 'activity*.zip']

        for pattern in patterns:
            for file_path in current_dir.glob(pattern):
                archive.append(file_path.name)

        # Проверяем наличие всех архивов в директории
        errors = []
        
        # Проверка наличия в директории cat_dict
        cat_keys = [key for key in archive if key.startswith('cat_dict')]
        if not cat_keys:
            errors.append(">> В директории нет архива 'cat_dict*.zip'")

        # Проверка наличия в директории brand_dict
        brand_keys = [key for key in archive if key.startswith('brand_dict')]
        if not brand_keys:
            errors.append(">> В директории нет архива 'brand_dict*.zip'")

        # Проверка наличия в директории activity
        activity_keys = [key for key in archive if key.startswith('activity')]
        if not activity_keys:
            errors.append(">> В директории нет архива 'activity*.zip'")
        
        # Проверка наличия в директории соц.-дема
        if 'socdem' in note: 
            socdem_keys = [key for key in archive if key.startswith('socdem')]
            if not socdem_keys:
                errors.append(">> В директории нет архива 'socdem_dict*.zip'")

        if errors:
            for error in errors:
                print(f"{error}")
            return True

        # Получаем из директории архив с файлами
        # Для блокнотов socdem необходимо наличие данных за период минус 2 месяца, в ином случае - существующий
        if 'socdem' in note and period is not None:
            dates = [datetime.strptime(d, '%Y-%m-%d') for d in period]
            earliest_date = min(dates)

            # Генерируем недостающие 2 месяца
            extra_months = [(earliest_date - relativedelta(months=i)).strftime('%Y-%m-01') 
                            for i in range(2, 0, -1)]

            period_new = extra_months + period
            archive_dict = FileApi().open_zip(archives=archive, periods=period_new)
        else:
            archive_dict = FileApi().open_zip(archives=archive, periods=period)
        
        #print(archive_dict.keys())
        
        # Фильтр demo_filter может быть применен только в блокнотах socdem
        # Проверка: demo_filter может быть True только при note='socdem'
        
        if 'socdem' not in note and demo_filter not in (False,None):
            print(">> Для применения 'demo_filter' воспользуйтель блокнотом FileApi_calculation_demography или FileApi_calculation_demography_SoS")
            demo_filter = False
            
      


        # Формируем из каждого файла с активностью датафреймы 
        df = pd.DataFrame()
        # Формируем из каждого файла с соц.-дем датафреймы
        df_socdem = pd.DataFrame()
        
        # Нужные колонки
        col = ['month', 'Category', 'Brand', 'ResourceType', 'Weight']
        # Колонки для соц.-дема (SubjectID необходим для расчета Sample в socdem)
        col_sd = ['month', 'Category', 'Brand', 'ResourceType','SubjectID', 'Weight', 'Sex', 'Age_group','Income','Region']

        if not any('activity' in key for key in archive_dict.keys()):
            print('>> Проверьте файл с активностью и период. Активность за указанный период отсутствует')
            data = df.copy()
        elif 'socdem' in note and not any('socdem_dict' in key for key in archive_dict.keys()):
            print('>> Проверьте файл с соц.-дем и период. Соц.-дем за указанный период отсутствует')
            data = df.copy()
        else:
            for file in archive_dict.keys():
                if file.startswith("activity"):
                    df = pd.concat([df, archive_dict[f'{file}']], ignore_index=False)
                if file.startswith("socdem_dict"):
                    df_socdem = pd.concat([df_socdem, archive_dict[f'{file}']], ignore_index=False)
            # Формируем итоговый датафрейм с данными об активности, с названиями брендов и категорий
            # Джойн словарей inner
            if 'socdem' in note:               
                 data = (df.merge(df_socdem, on=['SubjectID', 'month'])
                    .merge(archive_dict['brand_dict'], on='BrandID')
                    .merge(archive_dict['cat_dict'], on=['Category1ID', 'Category2ID', 'Category3ID'])
                    .rename(columns={'DashboardCategory': 'Category'})
                   )[col_sd]
            else:
                 data = (df
                    .merge(archive_dict['brand_dict'], on='BrandID')
                    .merge(archive_dict['cat_dict'], on=['Category1ID', 'Category2ID', 'Category3ID'])
                    .rename(columns={'DashboardCategory': 'Category'})
                   )[col]
                
                

        # Проверка параметров и применение фильтров
        errors = []

        if len(data) == 0:
            errors.append('>> Для расчета показателей загрузите недостающий(ие) архив(ы)')

        # Если блокнот с расчетом по категориям
        if note == 'category':
            if not isinstance(period, list) and period is not None:
                errors.append(">> Значение 'period' должно быть в формате: ['YYYY-MM-01', 'YYYY-MM-01']")

            if not isinstance(category_filter, list) and category_filter is not None:
                errors.append(">> Указанная категория не найдена. Значение 'category_filter' должно быть в формате: ['Категория1']")

            if not isinstance(flag_filter, bool):
                errors.append(">> Значение 'flag_filter' должно быть в формате: True или False")
                

            if errors:
                for error in errors:
                    print(f"{error}")
            else:
                if category_filter:
                    data_filt = data[data['Category'].isin(category_filter)]
                    if data_filt.empty:
                        errors.append(">> Указанная категория не найдена. Проверьте заданную категорию.")
                else:
                    data_filt = data.copy()

                if flag_filter:
                    data_filt = data_filt.copy()
                else:
                    data_filt = data_filt.copy()
                    data_filt['ResourceType'] = np.where(data_filt['ResourceType'] != 'Поисковики', 
                                                         'Все e-com ресурсы', data_filt['ResourceType'])

                if errors:
                    for error in errors:
                        print(f"{error}")
                else:
                    return data_filt

        # Если блокнот с расчетом по брендам
        elif note == 'brand':
            if not isinstance(period, list) and period is not None:
                errors.append(">> Значение 'period' должно быть в формате: ['YYYY-MM-01', 'YYYY-MM-01']")

            if not isinstance(category_filter, str):
                errors.append(">> Указанная категория не найдена. Значение 'category_filter' должно быть в формате: 'Категория'")
                
            if not isinstance(brand_filter, list) and brand_filter is not None:
                errors.append(">> Указанный бренд не найден. Значение 'brand_filter' должно быть в формате: ['бренд1', 'бренд2']")
                
            
            if errors:
                for error in errors:
                    print(f"{error}")
            else:
                if category_filter:
                    data_filt = data[data['Category']==category_filter]
                    if data_filt.empty:
                        errors.append(">> Указанная категория не найдена. Проверьте заданную категорию.")
                else:
                    data_filt = data.copy()
                    
                if brand_filter:
                    data_filt = data_filt[(data_filt['Brand'].isin(brand_filter)) & (data_filt['Category'] == category_filter)]
                    
                    # Проверяем нет ли потерянных брендов 
                    existing_brands = set(data_filt['Brand'].unique())
                    requested_brands = set(brand_filter)
                    missing_brands = requested_brands - existing_brands
                    
                    if missing_brands:
                        missing_brands_str = ', '.join(missing_brands)
                        errors.append(f">> Следующие бренды не найдены в данных: {missing_brands_str}")
                        
                    if data_filt.empty:
                        errors.append(">> Указанный бренд не найден. Проверьте заданные категорию и бренд.")
                else:
                    data_filt = data_filt[data_filt['Category'] == category_filter]

                if flag_filter:
                    data_filt = data_filt.copy()
                else:
                    data_filt = data_filt.copy()
                    data_filt['ResourceType'] = np.where(data_filt['ResourceType'] != 'Поисковики', 
                                                         'Все e-com ресурсы', data_filt['ResourceType'])
                
                if errors:
                    for error in errors:
                        print(f"{error}")
                else:
                    return data_filt

        # Если блокнот с расчетом по брендам sos
        elif note == 'brand_sos':
            if not isinstance(period, list) and period is not None:
                errors.append(">> Значение 'period' должно быть в формате: ['YYYY-MM-01', 'YYYY-MM-01']")

            if not isinstance(category_filter, str):
                errors.append(">> Указанная категория не найдена. Значение 'category_filter' должно быть в формате: 'Категория'")

            if not isinstance(brand_filter, list) and brand_filter is not None:
                errors.append(">> Указанный бренд не найден. Значение 'brand_filter' должно быть в формате: ['бренд1', 'бренд2']")
            
            
            if errors:
                for error in errors:
                    print(f"{error}")
            else:
                if category_filter:
                    data_filt = data[data['Category']==category_filter]
                    data_all = data[data['Category']==category_filter]
                    if data_filt.empty:
                        errors.append(">> Указанная категория не найдена. Проверьте заданную категорию.")
                else:
                    data_filt = data.copy()
                    data_all = data.copy()
                    
                if brand_filter:
                    data_filt = data_filt[data_filt['Brand'].isin(brand_filter)]
                    
                    # Проверяем нет ли потерянных брендов 
                    existing_brands = set(data_filt['Brand'].unique())
                    requested_brands = set(brand_filter)
                    missing_brands = requested_brands - existing_brands
                    
                    if missing_brands:
                        missing_brands_str = ', '.join(missing_brands)
                        errors.append(f">> Следующие бренды не найдены в данных: {missing_brands_str}")
                        
                    if data_filt.empty:
                        errors.append(">> Указанный бренд не найден. Проверьте заданные категорию и бренд.")
                
                
                if errors:
                    for error in errors:
                        print(f"{error}")
                        return False, False
                else:
                    return data_filt, data_all
                
        # Если блокнот с расчетом по socdem
        elif note == 'socdem' or note == 'socdem_sos':
            if not isinstance(period, list) and period is not None:
                errors.append(">> Значение 'period' должно быть в формате: ['YYYY-MM-01', 'YYYY-MM-01']")  
                
            if category_filter is None or not isinstance(category_filter, str):
                errors.append(">> Указанная категория не найдена. Значение 'category_filter' должно быть в формате: 'Категория'")
                
            if not isinstance(brand_filter, list) and brand_filter is not None:
                errors.append(">> Указанный бренд не найден. Значение 'brand_filter' должно быть в формате: ['бренд1', 'бренд2']")
                
            if not isinstance(demo_filter, str) or demo_filter not in data.columns:
                errors.append(">> Указанный соц.-дем параметр не найден. Пожалуйста, проверьте заданный параметр.")
                
                
            if errors:
                for error in errors:
                    print(f"{error}")
                if note == 'socdem_sos':
                    return None,None
                else:
                    return None
            else:
                
                if category_filter:
                    data_filt = data[data['Category']==category_filter]
                    data_all = data[data['Category']==category_filter][['month','Category','Weight',demo_filter]]
                    if data_filt.empty:
                        errors.append(">> Указанная категория не найдена. Проверьте заданную категорию.")
                
                if brand_filter:
                    data_filt = data_filt[data_filt['Brand'].isin(brand_filter)]
                    
                    # Проверяем нет ли потерянных брендов 
                    existing_brands = set(data_filt['Brand'].unique())
                    requested_brands = set(brand_filter)
                    missing_brands = requested_brands - existing_brands
                    
                    if data_filt.empty:
                        errors.append(">> Пожалуйста, проверьте заданные категорию и бренд.")
                    if missing_brands:
                        missing_brands_str = ', '.join(missing_brands)
                        errors.append(f">> Следующие бренды не найдены в данных: {missing_brands_str}")
                        
                # Определяем, что данных достаточно
                n_month = 3

                unique_months = sorted(data['month'].unique())

                if len(unique_months) < n_month:
                    errors.append(">> Пожалуйста, проверте загруженные архивы activity.zip и socdem_dict.zip. Загрузите архивы не менее чем за 3 последних месяца.")
                        
                        
                if errors:
                    for error in errors:
                        print(f"{error}")
                    if note == 'socdem_sos':
                        return None,None
                    else:
                        return None  
                    
                else:

                
                    if demo_filter == 'Sex':
                        data_filt = data_filt.copy()
                        data_filt = data_filt.drop(['Age_group','Income','Region'], axis=1)
                    elif demo_filter == 'Age_group':
                        data_filt = data_filt.copy()
                        data_filt = data_filt.drop(['Sex','Income','Region'], axis=1)
                    elif demo_filter == 'Income':
                        data_filt = data_filt.copy()
                        data_filt = data_filt.drop(['Sex','Age_group','Region'], axis=1)
                    elif demo_filter == 'Region':
                        data_filt = data_filt.copy()
                        data_filt = data_filt.drop(['Sex','Age_group','Income'], axis=1)


                    # Проверка, что выборка достаточная
                    #Получаем df для расчетов с нормальной выборкой
                    data_filt = self.calculate_sample(data=data_filt, demo_filter=demo_filter,category_filter=category_filter,brand_filter=brand_filter, brand_flag=brand_flag)

                    if data_filt.empty:
                        errors.append(">> Выборка недостаточна для дальнейших расчетов. Пожалуйста, измените фильтры")

                    # Для дальнейшей работы ф-ии create_pivot сохраняем note
                    self._note = note

                    if errors:
                        for error in errors:
                            print(f"{error}")
                        if note == 'socdem_sos':
                            return None,None
                        else:
                            return None
                    else:
                        if note == 'socdem':
                            return data_filt
                        if note == 'socdem_sos':
                            return data_filt, data_all
                
        else:
            print(">> Неверное значение параметра 'note'. Допустимые значения: 'category' или 'brand' или 'brand_sos' или 'socdem' или 'socdem_sos'")
            return True
    
    
    def draw_diagram(self, df, period, col, brand_cat):
        if (period is not None and len(period) == 1) or (df['month'].nunique() == 1):
            print('>> Выбран только один месяц.\n>> Для построения графика с динамикой количества запросов по месяцам укажите несколько месяцев (от двух).\n')
        else:
            df['month'] = pd.to_datetime(df['month'])
            # строим график
            fig_qcnt = px.line(df, 
                          x='month', 
                          y=col, 
                          color=brand_cat)

            # форматирование графика
            fig_qcnt.update_layout(
                {'plot_bgcolor': 'rgba(0, 0, 0, 0)',
                'paper_bgcolor': 'rgba(0, 0, 0, 0)'},
                xaxis_title=None,
                yaxis_title=None
            ).update_layout(yaxis_range=[0, None])
            
            months = sorted(df['month'].dt.to_period('M').unique())
            tickvals = [pd.Timestamp(month.start_time) for month in months]

            fig_qcnt.update_xaxes(
                tickvals=tickvals,
                tickmode='array',
                tickformat="%b\n%Y",
                fixedrange=True
            )
            
            print('>> Динамика показателя по месяцам')
            fig_qcnt.show()
            df['month'] = pd.to_datetime(df['month']).dt.strftime('%Y-%m-%d')
            
    def calculate_sample(self, data, demo_filter, brand_filter=None, category_filter=None, brand_flag=None):
        """
        Рассчитывает размер выборки в зависимости от среза

        Срезы:
        1. Совокупная выборка по брендам
        2. Выборка по каждому отдельному бренду внутри категории
        """
        if data is None or data is True:
            print(f">> Отсутствуют необходимые данные.")
            return None
        else:
            # Определяем срез расчета на основе фильтров

            #если brand_flag = False - совокупный расчет брендов
            if brand_flag == False:
                # Совокупная выборка (фактически по категории, формируем "совокупный" бренд)
                
                # Группируем и объединяем все бренды в одну строку
                brand_agg = data.groupby(['month', 'Category'])['Brand'].agg(lambda x: ', '.join(sorted(x.unique()))).reset_index()

                # Присоединяем колонку к исходным данным
                data = data.merge(brand_agg, on=['month', 'Category'], suffixes=('', '_merged'))
                
                # Проверяем количество брендов и заменяем на "группа брендов >5"
                def format_brands(brand_string):
                    brands_list = [b.strip() for b in brand_string.split(',')]
                    if len(brands_list) > 5:
                        return "группа брендов >5"
                    return brand_string
                # Применяем форматирование
                data['Brand_merged'] = data['Brand_merged'].apply(format_brands)

                # Заменяем колонку Brand на объединенную
                data['Brand'] = data['Brand_merged']
                data = data.drop('Brand_merged', axis=1)


            # Определяем выборку в каждом месяце
            group_col = ['Category','Brand']
            sample_df = (data.groupby(['month']+group_col)['SubjectID']
                        .nunique()
                        .reset_index(name='sample_size'))

            
            # Сортируем по месяцам
            sample_df = sample_df.sort_values('month')

            # Ф-ия роллинг суммы по каждой группе
            # Сортируем по месяцам
            # Рассчитываем скользящую сумму за 3 месяца, окно = n_month, минимум значений = n_month
            n_month = 3
            def calc_rolling_sum(group):
                group = group.sort_values('month')
                group['rolling_sum'] = group['sample_size'].rolling(window=n_month, min_periods=n_month).sum()
                return group

            # рассчитываем
            sample_df = sample_df.groupby(group_col).apply(calc_rolling_sum).reset_index(drop=True)

            # Удаляем строки, где нет полного окна
            # Например, при period = None данные будут доступны с сентября (минус 2 месяца)
            sample_df = sample_df.dropna(subset=['rolling_sum'])

            # Среднее за окно = n_month
            sample_df['mean_sample_size'] = sample_df['rolling_sum'] / n_month


            # Определяем достаточный ли размер выборки
            def get_sample_size(mean_value):
                if mean_value >= 20:
                    return 'normal'
                else:
                    return 'small'

            # Определяем размер
            sample_df['sample_size_category'] = sample_df['mean_sample_size'].apply(get_sample_size)
            # Оставляем только нормальную выборку
            normal_sample = sample_df[sample_df['sample_size_category'] != 'small'][['month'] + group_col].drop_duplicates()
            
            # Получаем полный отфильтрованный датасет с необходимыми полями
            data_filtered = data.merge(normal_sample[['month']+ group_col], on=['month']+group_col).drop(['ResourceType'], axis=1)

            return data_filtered
        
            

    
    def create_pivot(self, data, demo_filter, values_order=['QCnt000_param', '%']):
        """
        Создает сводную таблицу данных соц.-дема
        """
        # Создаем сводную таблицу
        pivot_share = data.pivot_table(
            index=['Category','Brand','month','QCnt000'],
            columns=demo_filter,
            values=values_order,
            fill_value=0
        )

        # Сортируем колонки в нужном порядке
        pivot_share = pivot_share.reindex(values_order, level=0, axis=1)

        # Заполняем и соединяем колоноки
        pivot_share.columns = [f'{col[0]}_{col[1]}' for col in pivot_share.columns]
        
        # Переименовываем колонки: убираем "_param" из названий
        pivot_share.columns = [col.replace('QCnt000_param_', 'QCnt000_') for col in pivot_share.columns]

        # Переименовываем колонки для блокнота socdem_sos
        if self._note == 'socdem_sos':
            pivot_share.columns = [col.replace('SoS_%_', 'SoS_') for col in pivot_share.columns]
            
        pivot_share = pivot_share.reset_index()
        
        
        return pivot_share


# In[ ]:


import requests
import json
import os

import csv
import pandas as pd
import numpy as np
import zipfile
    
import datetime as dt
from datetime import date
from datetime import datetime
from datetime import timedelta
import glob
import plotly.express as px
from typing import Union

from pathlib import Path

from dateutil.relativedelta import relativedelta
import re



class FileApi:
    def create_url(self, filetype: str = '', period: str = 'list', method: str = 'list', payload_agency: str = '') -> str:
        """
        Формирует URL для API Mediascope на основе параметров.

        Параметры:
            filetype: Тип файла ('category_dict' - словарь категорий, 'brand_dict' - словарь брендов, 
                                 'socdem_dict' - словарь соц.-дема, 'activity' - активность)
            period: Период для фильтрации файла с активностью и словаря соц.-дема
            method: Метод API ('list' - для получения списка файлов, 'download' - для скачивания)

        """
        # Неизменяемая часть URL
        url_base = 'https://api.mediascope.net/file-delivery/api/v1/'
        # Проект
        project = 'projectName=share_of_search'
        agency = payload_agency

        # Метод получения списка определенных файлов или всего списка файлов: Метод list
        if method == 'list':
            # В зависимости от типа файла, по умолчанию - все файлы
            if filetype == 'cat_dict' or filetype == 'brand_dict':  # для просмотра словарей
                return f'{url_base}list?{project}&filterText={agency}/{filetype}/**'
            elif (filetype=='activity' or filetype=='socdem_dict') and period:  # для просмотра активности и соц.-дема с фильтром по периоду
                return f'{url_base}list?{project}&filterText={agency}/{filetype}/month={period[0]}/**'
            elif (filetype=='activity' or filetype=='socdem_dict'):  # для просмотра активности и соц.-дема за весь период
                return f'{url_base}list?{project}&filterText={agency}/{filetype}/**'
            else:  # для просмотра всех файлов
                return f'{url_base}list?{project}&filterText={agency}/**'

        # Метод скачивания файлов: download
        elif method == 'download':
            # В зависимости от типа файла, по умолчанию - все файлы
            if filetype == 'cat_dict' or filetype == 'brand_dict':
                return f'{url_base}downloadZip?{project}&files={agency}/{filetype}/*.csv'
            elif (filetype=='activity' or filetype=='socdem_dict') and period:  # для скачивания активности и соц.-дема с фильтром по периоду
                return f'{url_base}downloadZip?{project}&files={agency}/{filetype}/month={period[0]}/**'
            elif (filetype=='activity' or filetype=='socdem_dict'):  # для скачивания активности и соц.-дема за весь период
                return f'{url_base}downloadZip?{project}&files={agency}/{filetype}/**'
            else:  # для скачивания всех файлов
                return f'{url_base}downloadZip?{project}&files={agency}/**'
        else:
            raise ValueError(f"Unknown method: {method}")
        
    
    
    # функция для работы с File API
    def File_Api_Mediascope(self, filetype: str = '', period: str = '', method: str = 'list', token: str = '', payload_agency: str = ''):
        """
        Функция
            - получает токен
            - выполняет запросы к API для получения списка файлов (метод list) или скачивания архива с файлами (метод download).

        Параметры:
            filetype: Тип файла ('category_dict' - словарь категорий, 'brand_dict' - словарь брендов,
                                 'socdem_dict' - словарь соц.-дема, 'activity' - активность)
            period: Период для фильтрации файла с активностью и словаря соц.-дема
            method: Метод API ('list' - для получения списка файлов, 'download' - для скачивания)
            token: Токен для авторизации
        """
        
        token, payload_agency = FileApi().get_token_deliv()
        # Формирование заголовков для авторизации   
        headers = {
            'Authorization': f'Bearer {token}',
        }

        # Получаем URL с помощью функции create_url
        url = self.create_url(filetype=filetype, period=period, method=method, payload_agency=payload_agency)
        
        # Дата для названия файла
        time_now = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Для проверки даты при download activity и socdem_dict
        date_pattern = r'^\d{4}-\d{2}-01$'
        
        # Выполнение GET запроса, ответ от сервера сохраняем в response
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            if method == 'list':  # для метода list
                list_response = response.json()  # если запрос успешен, возвращаются данные в формате json

                files_info = [
                    (', '.join(file_info.get('file', '').split('/')[:3] if len(file_info.get('file').split('/')) > 3
                     else file_info.get('file', '').split('/')[:2]),  # выводится только значимая часть названия
                     file_info.get('lastUpdatedDate', '').split('T')[0])  # и дата обновления
                    for file_info in list_response if file_info.get('file')
                ]

                files_info.sort(key=lambda x: x[0], reverse=False)  # сортировка по названию файла
                
                for file_name, file_update in files_info:
                    print(f"File_name: {file_name}, Update: {file_update}")  # вывод списка файлов с указанием даты обновления

            elif method == 'download':
                if period and (filetype=='activity' or filetype=='socdem_dict'):
                    if not isinstance(period, list) and period is not None or not re.match(date_pattern, period[0]):
                        print("Значение 'period' должно быть в формате: ['YYYY-MM-01']")
                        return None
                    else:
                        period = period[0].replace('[', '').replace(']', '')
                        zip_filename = f'{filetype}_{period}-{time_now}.zip'
                elif period is None and (filetype=='activity' or filetype=='socdem_dict'):
                    zip_filename = f'{filetype}.zip'
                elif filetype == 'cat_dict' or filetype == 'brand_dict':
                    zip_filename = f'{filetype}-{time_now}.zip'
                elif filetype is None and period:
                    zip_filename = f'all_filetype-{time_now}.zip'
                else:
                    print('Задание сформировано некорректно.')
                    return None
                with open(zip_filename, 'wb') as file:
                    file.write(response.content)  # если запрос успешен, записать файл в архив
                return zip_filename
        else:
            if response.status_code == 401:
                print(f'Ошибка: {response.status_code}. Проблема с аутентификацией. Проверьте username, password в keys_file_api.txt')
            elif response.status_code == 400:
                print(f'Ошибка: {response.status_code}. Синтаксическая ошибка.\n\nВозможные ошибки:\n1. Неправильно указан период (или данных за этот период нет в вашей поставке)\n\nЕсли ошибка остается, напишите нам')
            elif response.status_code == 403:
                print(f'Ошибка: {response.status_code}. Что-то не так с правами доступа. Пишите нам')
            elif response.status_code == 404:
                print(f'Ошибка: {response.status_code}. Запрашиваемые данные не найдены. Пишите нам')
            else:
                print(f'Ошибка: {response.status_code}')

            return None
        
        
    def get_token_deliv(self):
        
        """
        Получает токен для работы с fileapi
        """
        # URL, необходимый для получения токена
        url_token = "https://auth.mediascope.net/auth/realms/mediascope/protocol/openid-connect/token"
        
        #Данные для аутентификации.Ключи и значения прописаны в txt 
        payload = {}
        empty_fields = []
        extra_space = []
        with open ('keys_file_api.txt', 'r', encoding='utf-8') as f:
            for line in f:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    # проверяем пробелы
                    if ' ' in line:
                        extra_space.append(key)
                        print(f'В файле keys_file_api.txt в строке "{key}" лишний пробел')
                    if not value:
                        empty_fields.append(key)
                        print(f'В файле keys_file_api.txt заполните поле "{key}"')
                    payload[key]=value
        
        # если есть синтаксические ошибки в txt файле
        if empty_fields or extra_space:
            print('Внесите изменения в "keys_file_api.txt"')
            error_found = True
        
        # Отправка POST-запроса для получения токена
        response_token = requests.post(url_token, data=payload)

        # Проверка, что запрос прошел успешно
        if response_token.status_code == 200:
            # Парсим полученный JSON с токеном
            token = response_token.json().get('access_token')#если запрос успешен, получен токен
            #print("Токен получен")
            return token, payload['agency']
        else:
            return False, False
    
    
    
    def open_zip(self, archives: list = None, periods: list = None):
        """
        Открывает несколько ZIP-архивов и извлекает CSV файлы

        """
        if archives is None:
            archives = []

        all_data = {}

        # Сортируем архивы по типу и дате
        cat_archives = []
        brand_archives = []
        activity_archives = []
        socdem_archives = []

        for archive in archives:
            if not archive.lower().endswith('.zip'):
                continue

            archive_name = os.path.basename(archive).lower().replace('.zip', '')

            if archive_name.startswith('cat_dict-'):
                cat_archives.append(archive)
            elif archive_name.startswith('brand_dict-'):
                brand_archives.append(archive)
            elif archive_name.startswith('activity'):
                activity_archives.append(archive)
            elif archive_name.startswith('socdem_dict'):
                socdem_archives.append(archive)

        # Берем самый свежий cat_dict (последний после сортировки)
        if cat_archives:
            cat_archives.sort()  # Сортировка по алфавиту = по дате
            latest_cat = cat_archives[-1]
            
            with zipfile.ZipFile(latest_cat, 'r') as zip_ref:
                for filename in zip_ref.namelist():
                    if filename.lower().endswith('.csv'):
                        with zip_ref.open(filename) as file:
                            df = pd.read_csv(file, low_memory=False, encoding='cp1251')
                            all_data['cat_dict'] = df
                        break

        # Берем самый свежий brand_dict
        if brand_archives:
            brand_archives.sort()
            latest_brand = brand_archives[-1]

            with zipfile.ZipFile(latest_brand, 'r') as zip_ref:
                for filename in zip_ref.namelist():
                    if filename.lower().endswith('.csv'):
                        with zip_ref.open(filename) as file:
                            df = pd.read_csv(file, low_memory=False, encoding='cp1251')
                            all_data['brand_dict'] = df
                        break

        # Обрабатываем activity архивы
        for archive in activity_archives:
            with zipfile.ZipFile(archive, 'r') as zip_ref:
                for filename in zip_ref.namelist():
                    if filename.lower().endswith('.csv'):
                        file_basename = os.path.basename(filename).lower().replace('.csv', '')

                        if periods:
                            # Извлекаем период из имени
                            if 'activity_' in file_basename:
                                file_period = file_basename.replace('activity_', '')
                            else:
                                file_period = file_basename.replace('activity', '')

                            file_period = file_period.strip("[]'\"")

                            if file_period in periods and file_basename not in all_data:
                                with zip_ref.open(filename) as file:
                                    df = pd.read_csv(file, low_memory=False, encoding='cp1251')
                                    all_data[file_basename] = df
                        else:
                            if file_basename not in all_data:
                                with zip_ref.open(filename) as file:
                                    df = pd.read_csv(file, low_memory=False, encoding='cp1251')
                                    all_data[file_basename] = df
        # Обрабатываем соц.-дем архивы
        for archive in socdem_archives:
            with zipfile.ZipFile(archive, 'r') as zip_ref:
                for filename in zip_ref.namelist():
                    if filename.lower().endswith('.csv'):
                        file_basename = os.path.basename(filename).lower().replace('.csv', '')

                        if periods:
                            # Извлекаем период из имени
                            if 'socdem_dict_' in file_basename:
                                file_period = file_basename.replace('socdem_dict_', '')
                            else:
                                file_period = file_basename.replace('socdem_dict', '')

                            file_period = file_period.strip("[]'\"")

                            if file_period in periods and file_basename not in all_data:
                                with zip_ref.open(filename) as file:
                                    df = pd.read_csv(file, low_memory=False, encoding='cp1251')
                                    all_data[file_basename] = df
                        else:
                            if file_basename not in all_data:
                                with zip_ref.open(filename) as file:
                                    df = pd.read_csv(file, low_memory=False, encoding='cp1251')
                                    all_data[file_basename] = df
        return all_data
    
    
    def create_pdDF(self, period: list = None, note: str = None, 
                          category_filter: Union[str, list] = None, 
                          flag_filter: bool = None, 
                          demo_filter: str = None, 
                          brand_filter: list = None,
                            brand_flag: bool = None):
        """
        Создает pandas.DataFrame из архивов с файлами в директории и проверяет указанные фильтры

        """
        current_dir = Path.cwd()

        # Ищем файлы в директории
        archive = []
        patterns = ['cat_dict*.zip', 'brand_dict*.zip', 'socdem_dict*.zip', 'activity*.zip']

        for pattern in patterns:
            for file_path in current_dir.glob(pattern):
                archive.append(file_path.name)

        # Проверяем наличие всех архивов в директории
        errors = []
        
        # Проверка наличия в директории cat_dict
        cat_keys = [key for key in archive if key.startswith('cat_dict')]
        if not cat_keys:
            errors.append(">> В директории нет архива 'cat_dict*.zip'")

        # Проверка наличия в директории brand_dict
        brand_keys = [key for key in archive if key.startswith('brand_dict')]
        if not brand_keys:
            errors.append(">> В директории нет архива 'brand_dict*.zip'")

        # Проверка наличия в директории activity
        activity_keys = [key for key in archive if key.startswith('activity')]
        if not activity_keys:
            errors.append(">> В директории нет архива 'activity*.zip'")
        
        # Проверка наличия в директории соц.-дема
        if 'socdem' in note: 
            socdem_keys = [key for key in archive if key.startswith('socdem')]
            if not socdem_keys:
                errors.append(">> В директории нет архива 'socdem_dict*.zip'")

        if errors:
            for error in errors:
                print(f"{error}")
            return True

        # Получаем из директории архив с файлами
        # Для блокнотов socdem необходимо наличие данных за период минус 2 месяца, в ином случае - существующий
        if 'socdem' in note and period is not None:
            dates = [datetime.strptime(d, '%Y-%m-%d') for d in period]
            earliest_date = min(dates)

            # Генерируем недостающие 2 месяца
            extra_months = [(earliest_date - relativedelta(months=i)).strftime('%Y-%m-01') 
                            for i in range(2, 0, -1)]

            period_new = extra_months + period
            archive_dict = FileApi().open_zip(archives=archive, periods=period_new)
        else:
            archive_dict = FileApi().open_zip(archives=archive, periods=period)
        
        #print(archive_dict.keys())
        
        # Фильтр demo_filter может быть применен только в блокнотах socdem
        # Проверка: demo_filter может быть True только при note='socdem'
        
        if 'socdem' not in note and demo_filter not in (False,None):
            print(">> Для применения 'demo_filter' воспользуйтель блокнотом FileApi_calculation_demography или FileApi_calculation_demography_SoS")
            demo_filter = False
            
      


        # Формируем из каждого файла с активностью датафреймы 
        df = pd.DataFrame()
        # Формируем из каждого файла с соц.-дем датафреймы
        df_socdem = pd.DataFrame()
        
        # Нужные колонки
        col = ['month', 'Category', 'Brand', 'ResourceType', 'Weight']
        # Колонки для соц.-дема (SubjectID необходим для расчета Sample в socdem)
        col_sd = ['month', 'Category', 'Brand', 'ResourceType','SubjectID', 'Weight', 'Sex', 'Age_group','Income','Region']

        if not any('activity' in key for key in archive_dict.keys()):
            print('>> Проверьте файл с активностью и период. Активность за указанный период отсутствует')
            data = df.copy()
        elif 'socdem' in note and not any('socdem_dict' in key for key in archive_dict.keys()):
            print('>> Проверьте файл с соц.-дем и период. Соц.-дем за указанный период отсутствует')
            data = df.copy()
        else:
            for file in archive_dict.keys():
                if file.startswith("activity"):
                    df = pd.concat([df, archive_dict[f'{file}']], ignore_index=False)
                if file.startswith("socdem_dict"):
                    df_socdem = pd.concat([df_socdem, archive_dict[f'{file}']], ignore_index=False)
            # Формируем итоговый датафрейм с данными об активности, с названиями брендов и категорий
            # Джойн словарей inner
            if 'socdem' in note:               
                 data = (df.merge(df_socdem, on=['SubjectID', 'month'])
                    .merge(archive_dict['brand_dict'], on='BrandID')
                    .merge(archive_dict['cat_dict'], on=['Category1ID', 'Category2ID', 'Category3ID'])
                    .rename(columns={'DashboardCategory': 'Category'})
                   )[col_sd]
            else:
                 data = (df
                    .merge(archive_dict['brand_dict'], on='BrandID')
                    .merge(archive_dict['cat_dict'], on=['Category1ID', 'Category2ID', 'Category3ID'])
                    .rename(columns={'DashboardCategory': 'Category'})
                   )[col]
                
                

        # Проверка параметров и применение фильтров
        errors = []

        if len(data) == 0:
            errors.append('>> Для расчета показателей загрузите недостающий(ие) архив(ы)')

        # Если блокнот с расчетом по категориям
        if note == 'category':
            if not isinstance(period, list) and period is not None:
                errors.append(">> Значение 'period' должно быть в формате: ['YYYY-MM-01', 'YYYY-MM-01']")

            if not isinstance(category_filter, list) and category_filter is not None:
                errors.append(">> Указанная категория не найдена. Значение 'category_filter' должно быть в формате: ['Категория1']")

            if not isinstance(flag_filter, bool):
                errors.append(">> Значение 'flag_filter' должно быть в формате: True или False")
                

            if errors:
                for error in errors:
                    print(f"{error}")
            else:
                if category_filter:
                    data_filt = data[data['Category'].isin(category_filter)]
                    if data_filt.empty:
                        errors.append(">> Указанная категория не найдена. Проверьте заданную категорию.")
                else:
                    data_filt = data.copy()

                if flag_filter:
                    data_filt = data_filt.copy()
                else:
                    data_filt = data_filt.copy()
                    data_filt['ResourceType'] = np.where(data_filt['ResourceType'] != 'Поисковики', 
                                                         'Все e-com ресурсы', data_filt['ResourceType'])

                if errors:
                    for error in errors:
                        print(f"{error}")
                else:
                    return data_filt

        # Если блокнот с расчетом по брендам
        elif note == 'brand':
            if not isinstance(period, list) and period is not None:
                errors.append(">> Значение 'period' должно быть в формате: ['YYYY-MM-01', 'YYYY-MM-01']")

            if not isinstance(category_filter, str):
                errors.append(">> Указанная категория не найдена. Значение 'category_filter' должно быть в формате: 'Категория'")
                
            if not isinstance(brand_filter, list) and brand_filter is not None:
                errors.append(">> Указанный бренд не найден. Значение 'brand_filter' должно быть в формате: ['бренд1', 'бренд2']")
                
            
            if errors:
                for error in errors:
                    print(f"{error}")
            else:
                if category_filter:
                    data_filt = data[data['Category']==category_filter]
                    if data_filt.empty:
                        errors.append(">> Указанная категория не найдена. Проверьте заданную категорию.")
                else:
                    data_filt = data.copy()
                    
                if brand_filter:
                    data_filt = data_filt[(data_filt['Brand'].isin(brand_filter)) & (data_filt['Category'] == category_filter)]
                    
                    # Проверяем нет ли потерянных брендов 
                    existing_brands = set(data_filt['Brand'].unique())
                    requested_brands = set(brand_filter)
                    missing_brands = requested_brands - existing_brands
                    
                    if missing_brands:
                        missing_brands_str = ', '.join(missing_brands)
                        errors.append(f">> Следующие бренды не найдены в данных: {missing_brands_str}")
                        
                    if data_filt.empty:
                        errors.append(">> Указанный бренд не найден. Проверьте заданные категорию и бренд.")
                else:
                    data_filt = data_filt[data_filt['Category'] == category_filter]

                if flag_filter:
                    data_filt = data_filt.copy()
                else:
                    data_filt = data_filt.copy()
                    data_filt['ResourceType'] = np.where(data_filt['ResourceType'] != 'Поисковики', 
                                                         'Все e-com ресурсы', data_filt['ResourceType'])
                
                if errors:
                    for error in errors:
                        print(f"{error}")
                else:
                    return data_filt

        # Если блокнот с расчетом по брендам sos
        elif note == 'brand_sos':
            if not isinstance(period, list) and period is not None:
                errors.append(">> Значение 'period' должно быть в формате: ['YYYY-MM-01', 'YYYY-MM-01']")

            if not isinstance(category_filter, str):
                errors.append(">> Указанная категория не найдена. Значение 'category_filter' должно быть в формате: 'Категория'")

            if not isinstance(brand_filter, list) and brand_filter is not None:
                errors.append(">> Указанный бренд не найден. Значение 'brand_filter' должно быть в формате: ['бренд1', 'бренд2']")
            
            
            if errors:
                for error in errors:
                    print(f"{error}")
            else:
                if category_filter:
                    data_filt = data[data['Category']==category_filter]
                    data_all = data[data['Category']==category_filter]
                    if data_filt.empty:
                        errors.append(">> Указанная категория не найдена. Проверьте заданную категорию.")
                else:
                    data_filt = data.copy()
                    data_all = data.copy()
                    
                if brand_filter:
                    data_filt = data_filt[data_filt['Brand'].isin(brand_filter)]
                    
                    # Проверяем нет ли потерянных брендов 
                    existing_brands = set(data_filt['Brand'].unique())
                    requested_brands = set(brand_filter)
                    missing_brands = requested_brands - existing_brands
                    
                    if missing_brands:
                        missing_brands_str = ', '.join(missing_brands)
                        errors.append(f">> Следующие бренды не найдены в данных: {missing_brands_str}")
                        
                    if data_filt.empty:
                        errors.append(">> Указанный бренд не найден. Проверьте заданные категорию и бренд.")
                
                
                if errors:
                    for error in errors:
                        print(f"{error}")
                        return False, False
                else:
                    return data_filt, data_all
                
        # Если блокнот с расчетом по socdem
        elif note == 'socdem' or note == 'socdem_sos':
            if not isinstance(period, list) and period is not None:
                errors.append(">> Значение 'period' должно быть в формате: ['YYYY-MM-01', 'YYYY-MM-01']")  
                
            if category_filter is None or not isinstance(category_filter, str):
                errors.append(">> Указанная категория не найдена. Значение 'category_filter' должно быть в формате: 'Категория'")
                
            if not isinstance(brand_filter, list) and brand_filter is not None:
                errors.append(">> Указанный бренд не найден. Значение 'brand_filter' должно быть в формате: ['бренд1', 'бренд2']")
                
            if not isinstance(demo_filter, str) or demo_filter not in data.columns:
                errors.append(">> Указанный соц.-дем параметр не найден. Пожалуйста, проверьте заданный параметр.")
                
                
            if errors:
                for error in errors:
                    print(f"{error}")
                if note == 'socdem_sos':
                    return None,None
                else:
                    return None
            else:
                
                if category_filter:
                    data_filt = data[data['Category']==category_filter]
                    data_all = data[data['Category']==category_filter][['month','Category','Weight',demo_filter]]
                    if data_filt.empty:
                        errors.append(">> Указанная категория не найдена. Проверьте заданную категорию.")
                
                if brand_filter:
                    data_filt = data_filt[data_filt['Brand'].isin(brand_filter)]
                    
                    # Проверяем нет ли потерянных брендов 
                    existing_brands = set(data_filt['Brand'].unique())
                    requested_brands = set(brand_filter)
                    missing_brands = requested_brands - existing_brands
                    
                    if data_filt.empty:
                        errors.append(">> Пожалуйста, проверьте заданные категорию и бренд.")
                    if missing_brands:
                        missing_brands_str = ', '.join(missing_brands)
                        errors.append(f">> Следующие бренды не найдены в данных: {missing_brands_str}")
                        
                # Определяем, что данных достаточно
                n_month = 3

                unique_months = sorted(data['month'].unique())

                if len(unique_months) < n_month:
                    errors.append(">> Пожалуйста, проверте загруженные архивы activity.zip и socdem_dict.zip. Загрузите архивы не менее чем за 3 последних месяца.")
                        
                        
                if errors:
                    for error in errors:
                        print(f"{error}")
                    if note == 'socdem_sos':
                        return None,None
                    else:
                        return None  
                    
                else:

                
                    if demo_filter == 'Sex':
                        data_filt = data_filt.copy()
                        data_filt = data_filt.drop(['Age_group','Income','Region'], axis=1)
                    elif demo_filter == 'Age_group':
                        data_filt = data_filt.copy()
                        data_filt = data_filt.drop(['Sex','Income','Region'], axis=1)
                    elif demo_filter == 'Income':
                        data_filt = data_filt.copy()
                        data_filt = data_filt.drop(['Sex','Age_group','Region'], axis=1)
                    elif demo_filter == 'Region':
                        data_filt = data_filt.copy()
                        data_filt = data_filt.drop(['Sex','Age_group','Income'], axis=1)


                    # Проверка, что выборка достаточная
                    #Получаем df для расчетов с нормальной выборкой
                    data_filt = self.calculate_sample(data=data_filt, demo_filter=demo_filter,category_filter=category_filter,brand_filter=brand_filter, brand_flag=brand_flag)

                    if data_filt.empty:
                        errors.append(">> Выборка недостаточна для дальнейших расчетов. Пожалуйста, измените фильтры")

                    # Для дальнейшей работы ф-ии create_pivot сохраняем note
                    self._note = note

                    if errors:
                        for error in errors:
                            print(f"{error}")
                        if note == 'socdem_sos':
                            return None,None
                        else:
                            return None
                    else:
                        if note == 'socdem':
                            return data_filt
                        if note == 'socdem_sos':
                            return data_filt, data_all
                
        else:
            print(">> Неверное значение параметра 'note'. Допустимые значения: 'category' или 'brand' или 'brand_sos' или 'socdem' или 'socdem_sos'")
            return True
    
    
    def draw_diagram(self, df, period, col, brand_cat):
        if (period is not None and len(period) == 1) or (df['month'].nunique() == 1):
            print('>> Выбран только один месяц.\n>> Для построения графика с динамикой количества запросов по месяцам укажите несколько месяцев (от двух).\n')
        else:
            df['month'] = pd.to_datetime(df['month'])
            # строим график
            fig_qcnt = px.line(df, 
                          x='month', 
                          y=col, 
                          color=brand_cat)

            # форматирование графика
            fig_qcnt.update_layout(
                {'plot_bgcolor': 'rgba(0, 0, 0, 0)',
                'paper_bgcolor': 'rgba(0, 0, 0, 0)'},
                xaxis_title=None,
                yaxis_title=None
            ).update_layout(yaxis_range=[0, None])
            
            months = sorted(df['month'].dt.to_period('M').unique())
            tickvals = [pd.Timestamp(month.start_time) for month in months]

            fig_qcnt.update_xaxes(
                tickvals=tickvals,
                tickmode='array',
                tickformat="%b\n%Y",
                fixedrange=True
            )
            
            print('>> Динамика показателя по месяцам')
            fig_qcnt.show()
            df['month'] = pd.to_datetime(df['month']).dt.strftime('%Y-%m-%d')
            
    def calculate_sample(self, data, demo_filter, brand_filter=None, category_filter=None, brand_flag=None):
        """
        Рассчитывает размер выборки в зависимости от среза

        Срезы:
        1. Совокупная выборка по брендам
        2. Выборка по каждому отдельному бренду внутри категории
        """
        if data is None or data is True:
            print(f">> Отсутствуют необходимые данные.")
            return None
        else:
            # Определяем срез расчета на основе фильтров

            #если brand_flag = False - совокупный расчет брендов
            if brand_flag == False:
                # Совокупная выборка (фактически по категории, формируем "совокупный" бренд)
                
                # Группируем и объединяем все бренды в одну строку
                brand_agg = data.groupby(['month', 'Category'])['Brand'].agg(lambda x: ', '.join(sorted(x.unique()))).reset_index()

                # Присоединяем колонку к исходным данным
                data = data.merge(brand_agg, on=['month', 'Category'], suffixes=('', '_merged'))
                
                # Проверяем количество брендов и заменяем на "группа брендов >5"
                def format_brands(brand_string):
                    brands_list = [b.strip() for b in brand_string.split(',')]
                    if len(brands_list) > 5:
                        return "группа брендов >5"
                    return brand_string
                # Применяем форматирование
                data['Brand_merged'] = data['Brand_merged'].apply(format_brands)

                # Заменяем колонку Brand на объединенную
                data['Brand'] = data['Brand_merged']
                data = data.drop('Brand_merged', axis=1)


            # Определяем выборку в каждом месяце
            group_col = ['Category','Brand']
            sample_df = (data.groupby(['month']+group_col)['SubjectID']
                        .nunique()
                        .reset_index(name='sample_size'))

            
            # Сортируем по месяцам
            sample_df = sample_df.sort_values('month')

            # Ф-ия роллинг суммы по каждой группе
            # Сортируем по месяцам
            # Рассчитываем скользящую сумму за 3 месяца, окно = n_month, минимум значений = n_month
            n_month = 3
            def calc_rolling_sum(group):
                group = group.sort_values('month')
                group['rolling_sum'] = group['sample_size'].rolling(window=n_month, min_periods=n_month).sum()
                return group

            # рассчитываем
            sample_df = sample_df.groupby(group_col).apply(calc_rolling_sum).reset_index(drop=True)

            # Удаляем строки, где нет полного окна
            # Например, при period = None данные будут доступны с сентября (минус 2 месяца)
            sample_df = sample_df.dropna(subset=['rolling_sum'])

            # Среднее за окно = n_month
            sample_df['mean_sample_size'] = sample_df['rolling_sum'] / n_month


            # Определяем достаточный ли размер выборки
            def get_sample_size(mean_value):
                if mean_value >= 20:
                    return 'normal'
                else:
                    return 'small'

            # Определяем размер
            sample_df['sample_size_category'] = sample_df['mean_sample_size'].apply(get_sample_size)
            # Оставляем только нормальную выборку
            normal_sample = sample_df[sample_df['sample_size_category'] != 'small'][['month'] + group_col].drop_duplicates()
            
            # Получаем полный отфильтрованный датасет с необходимыми полями
            data_filtered = data.merge(normal_sample[['month']+ group_col], on=['month']+group_col).drop(['ResourceType'], axis=1)

            return data_filtered
        
            

    
    def create_pivot(self, data, demo_filter, values_order=['QCnt000_param', '%']):
        """
        Создает сводную таблицу данных соц.-дема
        """
        # Создаем сводную таблицу
        pivot_share = data.pivot_table(
            index=['Category','Brand','month','QCnt000'],
            columns=demo_filter,
            values=values_order,
            fill_value=0
        )

        # Сортируем колонки в нужном порядке
        pivot_share = pivot_share.reindex(values_order, level=0, axis=1)

        # Заполняем и соединяем колоноки
        pivot_share.columns = [f'{col[0]}_{col[1]}' for col in pivot_share.columns]
        
        # Переименовываем колонки: убираем "_param" из названий
        pivot_share.columns = [col.replace('QCnt000_param_', 'QCnt000_') for col in pivot_share.columns]

        # Переименовываем колонки для блокнота socdem_sos
        if self._note == 'socdem_sos':
            pivot_share.columns = [col.replace('SoS_%_', 'SoS_') for col in pivot_share.columns]
            
        pivot_share = pivot_share.reset_index()
        
        
        return pivot_share

