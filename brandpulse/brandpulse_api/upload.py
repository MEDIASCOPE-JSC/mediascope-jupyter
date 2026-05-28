import os
import glob
from .data import BrandpulseData
from .duckdb import DuckDbData


class BrandpulseUpload:
    # параметры загрузки даннных апи
    DOWNLOADS_DIR = 'packed_data'
    EXTRACT_DIR = 'unpacked_data'
    DB_FILE = 'brandpulse3.duckdb'
    
    # пути для загрузки/чтения данных
    DICTIONARY_DATA = f'{EXTRACT_DIR}/dictionary'
    ANSWER_DATA = f'{EXTRACT_DIR}/data/answer'
    WEIGHT_DATA = f'{EXTRACT_DIR}/data/weight'
    PROFILE_ANSWER_DATA = f'{EXTRACT_DIR}/data/profile/answer'
    PROFILE_WEIGHT_DATA = f'{EXTRACT_DIR}/data/profile/weight'
    BOOST_ANSWER_DATA = f'{EXTRACT_DIR}/data/profile/boost/answer'

    def __init__(self, db_file: str = DB_FILE, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # создаем объекты для работы
        self.api = BrandpulseData(download_dir=self.DOWNLOADS_DIR, extract_dir=self.EXTRACT_DIR)
        self.db = DuckDbData(db_file)
    
    def upload_projects(self, project_list: list):
        """
        Загрузка данных проектов
        
        Args:
            project_list: Список идентификаторов проектов
        """
        # получить данные проектов
        self.api.get_projects(project_ids=[str(i) for i in project_list])

        # Превращаем список в множество строк для быстрого поиска
        project_ids_str = set(map(str, project_list))

        # загрузка ответов
        for fpath in glob.glob(os.path.join(self.ANSWER_DATA, '*.csv.gz')):
            fname = os.path.basename(fpath)
            # Проверяем, есть ли какой-то из ID в названии файла
            if any(pid in fname for pid in project_ids_str):
                self.db.load_project_data_from_file(table_name="answer", file_path=fpath)

        # загрузка весов
        for fpath in glob.glob(os.path.join(self.WEIGHT_DATA, '*.csv.gz')):
            fname = os.path.basename(fpath)
            if any(pid in fname for pid in project_ids_str):
                self.db.load_project_data_from_file(table_name="weight", file_path=fpath)
        
        # получить бустовые данные проектов
        self.api.get_boost_answer(project_ids=[str(i) for i in project_list])

        # загрузка бустовых ответов для проектов
        for fpath in glob.glob(os.path.join(self.BOOST_ANSWER_DATA, '*.csv.gz')):
            fname = os.path.basename(fpath)
            if any(pid in fname for pid in project_ids_str):
                self.db.load_project_data_from_file(table_name="boost_answer", file_path=fpath)
    
    
    def upload_dicts(self):
        """
        Загрузка справочников
        
        """
        # получить список доступных проектов
        df_projects = self.api.get_available_projects()

        # сохраняем доступные проекты
        os.makedirs(self.EXTRACT_DIR, exist_ok=True)
        filepath = os.path.join(self.EXTRACT_DIR, 'projects.csv.gz')
        df_projects.to_csv(filepath, compression='gzip', index=False)
        print(f'Projects list successfully downloaded to {filepath}')

        # загрузка доступных проектов
        self.db.load_all_data_from_file(table_name="projects", file_path=f"{self.EXTRACT_DIR}/projects.csv.gz")

        # получить данные справочников
        self.api.get_dictionary()

        # загрузка словарей
        for fpath in glob.glob(os.path.join(self.DICTIONARY_DATA, '*.csv.gz')):
            self.db.load_all_data_from_file(table_name=os.path.basename(fpath).split('.')[0], file_path=fpath)
    
    
    def upload_profile(self, year: int):
        """
        Загрузка профиля
        
        Args:
            year: требуемый год
        """
        # получить данные профиля
        self.api.get_profile(year=year)

        # загрузка ответов для профиля
        for fpath in glob.glob(os.path.join(self.PROFILE_ANSWER_DATA, '*.csv.gz')):
            self.db.load_project_data_from_file(table_name="answer", file_path=fpath)

        # загрузка весов для профиля
        for fpath in glob.glob(os.path.join(self.PROFILE_WEIGHT_DATA, '*.csv.gz')):
            self.db.load_project_data_from_file(table_name="weight", file_path=fpath)

    