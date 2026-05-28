import time
import os
import re
import duckdb
from typing import Dict, List, Optional, Union


class DuckDbData:
    DEFAULT_DB_FILE = 'brandpulse1.duckdb'

    def __init__(self, db_file: str = DEFAULT_DB_FILE, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db_file = db_file

    def get_table_data(self, table_name: str):
        """
        Возвращает все данные из указанной таблицы в виде DataFrame.
        
        Args:
            table_name: Имя таблицы для чтения
        """
        with duckdb.connect(database=self.db_file) as con:
            return con.execute(f"SELECT * FROM {table_name}").fetchdf()

    def get_table_schema(self, table_name: str):
        """
        Возвращает схему указанной таблицы в виде DataFrame.
        
        Args:
            table_name: Имя таблицы для получения схемы
        """
        with duckdb.connect(database=self.db_file) as con:
            return con.execute(f"DESCRIBE {table_name}").fetchdf()

    def load_all_data_from_file(
        self,
        table_name: str,
        file_path: str
    ) -> Dict[str, Union[int, bool]]:
        """
        Полная замена данных в таблице из CSV файла.
        
        Args:
            table_name: Имя целевой таблицы в DuckDB
            file_path: Путь к CSV файлу с данными
            
        Returns:
            Словарь с результатами операции:
                - source_rows: количество строк в исходном файле
                - final_table_count: количество строк в таблице после загрузки
                - before_count: количество строк до операции
                - table_created: флаг создания новой таблицы
        """
        start_time = time.perf_counter()

        with duckdb.connect(database=self.db_file) as con:
            source_row_count = self._count_csv_rows(con, file_path)
            table_exists = self._check_table_exists(con, table_name)
            status = "замена" if table_exists else "создание"

            before_count = 0
            if table_exists:
                before_count = self._get_row_count(con, table_name)
                print(f"До {status}: {before_count} строк в '{table_name}'")
            else:
                print(f"Таблица '{table_name}' не существует → будет создана")

            if source_row_count == 0:
                print("⚠️  ПРЕДУПРЕЖДЕНИЕ: Исходный файл пустой!")
            else:
                print(f"🔄 {status.title()} содержимого таблицы '{table_name}'...")
                con.execute(f"""
                    CREATE OR REPLACE TABLE {table_name} AS
                    SELECT * FROM read_csv_auto(?)
                """, [file_path])

            final_count = self._get_row_count(con, table_name)
            print(f"Итого: {final_count} строк в '{table_name}'")

            self._verify_row_counts(source_row_count, final_count)
            con.execute("CHECKPOINT")

        self._print_operation_summary(
            f"Таблица '{table_name}' {status}",
            start_time, source_row_count, final_count, before_count
        )

        return {
            'source_rows': source_row_count,
            'final_table_count': final_count,
            'before_count': before_count,
            'table_created': not table_exists
        }

    def load_project_data_from_file(
        self,
        table_name: str,
        file_path: str,
        project_id: int = None
    ) -> Dict[str, int]:
        """
        Замена данных для конкретного project_id.
        - Удаляет старые данные для project_id
        - Загружает новые данные из CSV
        - Сохраняет данные других проектов
        
        Args:
            table_name: Имя целевой таблицы в DuckDB
            file_path: Путь к CSV файлу с данными
            project_id: ID проекта для обновления (по умолчанию None - берется из имени файла)
            
        Returns:
            Словарь с результатами операции:
                - source_rows: количество строк в исходном файле
                - before_count: количество строк проекта до операции
                - final_project_count: количество строк проекта после загрузки
        """
        if project_id is None:
            match = re.search(r'project_id=(\d+)', file_path)
            if match:
                project_id = int(match.group(1))
        
        start_time = time.perf_counter()
        temp_table = f"{table_name}_project_{project_id}_temp"

        with duckdb.connect(database=self.db_file) as con:
            source_row_count = self._count_csv_rows(con, file_path)
            
            # Проверка существования таблицы
            table_exists = self._check_table_exists(con, table_name)
            
            before_count = 0
            if table_exists:
                before_count = self._get_row_count(
                    con, table_name,
                    where_clause="project_id = $project_id",
                    params={"project_id": project_id}
                )
                print(f"До обновления: {before_count} строк для project_id={project_id}")
            else:
                print(f"Таблица '{table_name}' не существует → будет создана с данными project_id={project_id}")
            
            if source_row_count == 0:
                print(f"Внимание: Файл {file_path} пуст. Обновление отменено.")
                return {
                    'source_rows': 0,
                    'before_count': before_count,
                    'final_project_count': before_count # Данные не изменились
                }

            # Атомарное обновление данных проекта
            self._atomic_project_update(
                con, table_name, temp_table, file_path, project_id, table_exists
            )

            # Подсчет строк после обновления
            final_count = self._get_row_count(
                con, table_name,
                where_clause="project_id = $project_id",
                params={"project_id": project_id}
            )
            print(f"Итого: {final_count} строк для project_id={project_id}")

            self._verify_row_counts(source_row_count, final_count)
            con.execute("CHECKPOINT")

        self._print_operation_summary(
            f"Обновлено project_id={project_id}",
            start_time, source_row_count, final_count, before_count
        )

        return {
            'source_rows': source_row_count,
            'before_count': before_count,
            'final_project_count': final_count
        }

    def delete_project_data(
        self,
        project_ids: List[int],
        table_names: Optional[List[str]] = ['answer', 'boost_answer', 'weight']
    ) -> None:
        """
        Удаляет данные для указанных project_id из заданных таблиц.
        
        Args:
            project_ids: Список ID проектов для удаления
            table_names: Список имен таблиц (по умолчанию: answer, boost_answer, weight)
        """
        if not project_ids:
            return

        start_time = time.perf_counter()

        with duckdb.connect(database=self.db_file) as con:
            ids_str = ', '.join(str(pid) for pid in project_ids)
            filter_clause = f"WHERE project_id IN ({ids_str})"

            for table in table_names:
                con.execute(f"DELETE FROM {table} {filter_clause}")

            con.execute("CHECKPOINT")

        self._print_elapsed_time("Data deleted", start_time)

    # Упрощенные методы-алиасы
    def delete_all_project_data(self, project_ids: List[int]) -> None:
        """
        Удаляет данные весов и ответов для указанных project_id.
        
        Args:
            project_ids: Список ID проектов для удаления
        """
        self.delete_project_data(project_ids)

    def delete_table_project_data(self, project_ids: List[int], table_name: str) -> None:
        """
        Удаляет данные из конкретной таблицы для указанных project_id.
        
        Args:
            project_ids: Список ID проектов для удаления
            table_name: Имя таблицы для удаления данных
        """
        self.delete_project_data(project_ids, [table_name])

    def _count_csv_rows(self, con: duckdb.DuckDBPyConnection, file_path: str) -> int:
        """
        Подсчитывает количество строк в CSV файле.
        
        Args:
            con: Соединение с DuckDB
            file_path: Путь к CSV файлу
        """
        print(f"Подсчет строк в файле: {file_path}")
        # 1. Проверка на физическую пустоту (0 байт)
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            print(f"Файл {file_path} физически пуст или отсутствует.")
            return 0

        try:
            count = con.execute(
                "SELECT COUNT(*) FROM read_csv_auto(?, all_varchar=True)", 
                [file_path]
            ).fetchone()[0]
            print(f"Исходный файл содержит {count} строк")
            return count
        except Exception as e:
            # Если в GZ-архиве нет данных (даже заголовков), будет ошибка
            print(f"Ошибка при чтении (возможно, пустой архив): {e}")
            return 0

    def _get_row_count(
        self,
        con: duckdb.DuckDBPyConnection,
        table_name: str,
        where_clause: Optional[str] = None,
        params: Optional[Dict] = None
    ) -> int:
        """
        Подсчитывает количество строк в таблице с опциональным условием.
        
        Args:
            con: Соединение с DuckDB
            table_name: Имя таблицы
            where_clause: WHERE условие (опционально)
            params: Параметры для запроса (опционально)
        """
        query = f"SELECT COUNT(*) FROM {table_name}"
        if where_clause:
            query += f" WHERE {where_clause}"
        return con.execute(query, params or {}).fetchone()[0]

    def _check_table_exists(self, con: duckdb.DuckDBPyConnection, table_name: str) -> bool:
        """
        Проверяет существование таблицы в базе данных.
        
        Args:
            con: Соединение с DuckDB
            table_name: Имя таблицы для проверки
        """
        result = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
            [table_name]
        ).fetchone()[0]
        return result > 0

    def _verify_row_counts(self, source_count: int, final_count: int) -> None:
        """
        Проверяет соответствие количества строк в файле и таблице.
        
        Args:
            source_count: Количество строк в исходном файле
            final_count: Количество строк в итоговой таблице
        """
        if source_count != final_count:
            print(f"⚠️  ПРЕДУПРЕЖДЕНИЕ: {source_count} ≠ {final_count}")
        else:
            print("✅ Проверка соответствия количества строк в файле и таблице пройдена")

    def _atomic_project_update(
        self,
        con: duckdb.DuckDBPyConnection,
        table_name: str,
        temp_table: str,
        file_path: str,
        project_id: int,
        table_exists: bool
    ) -> None:
        """
        Выполняет атомарное обновление данных проекта.
        
        Создает временную таблицу с данными других проектов + новыми данными,
        затем атомарно заменяет основную таблицу.
        
        Args:
            con: Соединение с DuckDB
            table_name: Имя основной таблицы
            temp_table: Имя временной таблицы
            file_path: Путь к CSV файлу с новыми данными
            project_id: ID проекта для обновления
            table_exists: Флаг существования таблицы
        """
        print(f"🔄 Обновление project_id={project_id}...")

        if table_exists:
            # Создание временной таблицы с обновленными данными
            con.execute(f"""
                CREATE OR REPLACE TABLE {temp_table} AS
                SELECT * FROM {table_name} WHERE project_id != $project_id
                UNION ALL
                SELECT * FROM read_csv_auto($file_path)
            """, {"project_id": project_id, "file_path": file_path})

            # Атомарная замена таблиц
            backup_table = f"{table_name}_backup"
            con.execute(f"""
                DROP TABLE IF EXISTS {backup_table};
                ALTER TABLE {table_name} RENAME TO {backup_table};
                ALTER TABLE {temp_table} RENAME TO {table_name};
                DROP TABLE {backup_table};
            """)
        else:
            # Создание новой таблицы если не существует
            con.execute(f"""
                CREATE TABLE {table_name} AS
                SELECT * FROM read_csv_auto(?)
            """, [file_path])

    def _print_elapsed_time(self, operation: str, start_time: float) -> None:
        """
        Выводит время выполнения операции.
        
        Args:
            operation: Название операции
            start_time: Время начала операции
        """
        elapsed = time.perf_counter() - start_time
        minutes, seconds = divmod(elapsed, 60)
        print(f"{operation} in {int(minutes)} min {seconds:.3f} sec")

    def _print_operation_summary(
        self,
        operation: str,
        start_time: float,
        source_rows: int,
        final_count: int,
        before_count: int
    ) -> None:
        """
        Выводит итоговую статистику операции с количеством строк и временем.
        
        Args:
            operation: Название операции
            start_time: Время начала операции
            source_rows: Количество строк в исходном файле
            final_count: Итоговое количество строк
            before_count: Количество строк до операции
        """
        elapsed = time.perf_counter() - start_time
        minutes, seconds = divmod(elapsed, 60)
        net_change = final_count - before_count

        print(f"✅ {operation} за {int(minutes)} мин {seconds:.3f} сек")
        print(f"ИТОГО: {source_rows} → {final_count} [net: {net_change:+d}]")