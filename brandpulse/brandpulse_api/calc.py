"""Brandpulse metrics calculator using DuckDB."""

import duckdb
import pandas as pd


class BrandpulseCalc:
    """Calculator for brandpulse metrics using DuckDB."""

    DEFAULT_DB_FILE = "brandpulse1.duckdb"

    def __init__(self, db_file: str = DEFAULT_DB_FILE) -> None:
        """Initialize with database file path."""
        self.db_file = db_file

    def _build_property_option_filter(
        self,
        demo: list | None = None,
    ) -> str:
        """Build SQL conditions for property option filtering based on demo criteria."""
        if not demo:
            return ""

        filter_conditions = [
            f"(property_sys_name = '{item['property_name']}' "
            f"AND property_option_sys_name {item['expression']})"
            for item in demo
        ]

        return f"WHERE {' OR '.join(filter_conditions)}"

    def _execute_query(self, query: str, log_sql: bool = False) -> pd.DataFrame:
        """Execute SQL query and return result as DataFrame."""
        if log_sql:
            print("SQL query:")
            print(query)
            
        # Настройки для расширения лимита временных файлов
        sql_config = {
            'max_temp_directory_size': '100GiB',
            'temp_directory': 'duckdb_temp' # папка создастся рядом с кодом
    }

        with duckdb.connect(database=self.db_file, config=sql_config) as con:
            return con.execute(query).fetchdf()

    def _get_option_text(
        self,
        property_sys_name: str,
        option_sys_name: str,
    ) -> str:
        """Get property option text or default group label."""
        option_list = option_sys_name.split(" OR ")

        if len(option_list) == 1:
            query = f"""
                SELECT property_option_text
                FROM property_option
                WHERE property_option_sys_name = '{option_list[0]}'
                  AND property_id IN (
                      SELECT property_id
                      FROM property
                      WHERE property_sys_name = '{property_sys_name}'
                  )
            """
            result = self._execute_query(query)
            return result.iloc[0, 0] if not result.empty else option_sys_name

        return "группа значений"
    
    def _calc_universe(
        self,
        project_ids: list[int],
        dimension_type: str,  # 'property', 'category', 'brand'
        items: list[tuple],
        demo: list | None = None,
        log_sql: bool = False,
    ) -> pd.DataFrame:
        """
        Universal method to calculate universe distribution for one or multiple items.
        """
        property_option_filter = self._build_property_option_filter(demo)
        all_project_ids = ", ".join([str(i) for i in project_ids])
        num_projects = len(project_ids)
        
        demo_ctes = self._build_demo_filter_ctes(property_option_filter, demo)
        qualified_resp_cte = self._build_qualified_resp_cte(demo)
        
        # Общие CTE, которые будут использоваться во всех подзапросах
        base_ctes = f"""
        WITH {demo_ctes}
        relevant_answers AS (
            SELECT * 
            FROM answer a
            WHERE a.project_id IN ({all_project_ids}) 
                OR a.project_id IN (
                    SELECT parent_profile_id 
                    FROM projects 
                    WHERE project_id IN ({all_project_ids}) 
                )
            UNION ALL
            SELECT *
            FROM boost_answer b
            WHERE b.project_id IN ({all_project_ids}) 
        ),
        {qualified_resp_cte}
        """
        
        def build_case_expr(mapping, field, default_expr):
            if not mapping:
                return default_expr
            cases = [f"WHEN {field} = '{part}' THEN '{original}'" for part, original in mapping.items()]
            return f"CASE " + " ".join(cases) + f" ELSE {default_expr} END"
        
        # Строим SELECT для каждого элемента
        selects = []
        
        for item in items:
            if dimension_type == 'property':
                property_sys_name, option_sys_names = item[:2]
                option_text_param = item[2] if len(item) == 3 else None
                
                # Маппинг для опций
                option_parts_mapping = {}  # часть -> полное имя
                option_single_items = []   # отдельные элементы
                option_texts = {}          # полное имя -> текст (только для составных)
                
                for opt in option_sys_names:
                    if " OR " in opt:
                        # Составной элемент - может переопределяться
                        if len(option_sys_names) == 1:
                            if option_text_param:
                                option_texts[opt] = option_text_param
                            else:
                                option_texts[opt] = opt
                        for opt_part in opt.split(" OR "):
                            option_parts_mapping[opt_part] = opt
                    else:
                        # Обычный элемент - НЕ переопределяем, берем из базы
                        option_single_items.append(opt)
                
                # Формируем IN список
                in_parts = []
                in_parts.extend(option_parts_mapping.keys())
                in_parts.extend(option_single_items)
                all_option_parts = "', '".join(in_parts)
                
                # CASE для option_sys_name
                option_cases = []
                for part, full in option_parts_mapping.items():
                    option_cases.append(f"WHEN po.property_option_sys_name = '{part}' THEN '{full}'")
                for single in option_single_items:
                    option_cases.append(f"WHEN po.property_option_sys_name = '{single}' THEN '{single}'")
                
                if option_cases:
                    option_sys_expr = "CASE " + " ".join(option_cases) + f" ELSE po.property_option_sys_name END"
                else:
                    option_sys_expr = "po.property_option_sys_name"
                
                # option_text_expr: только для составных может быть переопределен
                option_text_expr = build_case_expr(option_texts, option_sys_expr, "po.property_option_text")
                
                select = f"""
                SELECT
                    p.property_sys_name,
                    p.property_text,
                    {option_sys_expr} AS option_sys_name,
                    {option_text_expr} AS option_text,
                    w.weight AS weight,
                    a.resp_id AS resp_id,
                    a.project_id AS project_id
                FROM relevant_answers a
                JOIN weight w ON a.resp_id = w.resp_id AND w.project_id = a.project_id
                JOIN property p ON a.property_id = p.property_id
                JOIN property_option po ON a.property_option_id = po.property_option_id
                WHERE p.property_sys_name = '{property_sys_name}' 
                AND po.property_option_sys_name IN ('{all_option_parts}')
                AND a.resp_id IN (SELECT resp_id FROM qualified_resp)
                """
                selects.append(select)
                
            elif dimension_type == 'category':
                property_sys_name, option_sys_names, category_sys_names = item[:3]
                option_text_param = item[3] if len(item) == 4 else None
                
                # Маппинг для опций
                option_parts_mapping = {}
                option_single_items = []
                option_texts = {}  # только для составных опций
                
                for opt in option_sys_names:
                    if " OR " in opt:
                        # Составной элемент - может переопределяться
                        if len(option_sys_names) == 1:
                            if option_text_param:
                                option_texts[opt] = option_text_param
                            else:
                                option_texts[opt] = opt
                        for opt_part in opt.split(" OR "):
                            option_parts_mapping[opt_part] = opt
                    else:
                        # Обычный элемент - НЕ переопределяем
                        option_single_items.append(opt)
                
                # Маппинг для категорий
                category_parts_mapping = {}
                category_single_items = []
                category_texts = {}  # для category_text (может переопределяться)
                
                for cat in category_sys_names:
                    if " OR " in cat:
                        # Составная категория
                        if option_text_param and len(category_sys_names) == 1:
                            category_texts[cat] = option_text_param
                        else:
                            category_texts[cat] = cat
                        for cat_part in cat.split(" OR "):
                            category_parts_mapping[cat_part] = cat
                    else:
                        # Обычная категория - НЕ переопределяем текст
                        category_single_items.append(cat)
                
                # Формируем IN списки
                in_option_parts = []
                in_option_parts.extend(option_parts_mapping.keys())
                in_option_parts.extend(option_single_items)
                all_option_parts = "', '".join(in_option_parts)
                
                in_category_parts = []
                in_category_parts.extend(category_parts_mapping.keys())
                in_category_parts.extend(category_single_items)
                all_category_parts = "', '".join(in_category_parts)
                
                # CASE для option_sys_name
                option_cases = []
                for part, full in option_parts_mapping.items():
                    option_cases.append(f"WHEN po.property_option_sys_name = '{part}' THEN '{full}'")
                for single in option_single_items:
                    option_cases.append(f"WHEN po.property_option_sys_name = '{single}' THEN '{single}'")
                
                if option_cases:
                    option_sys_expr = "CASE " + " ".join(option_cases) + f" ELSE po.property_option_sys_name END"
                else:
                    option_sys_expr = "po.property_option_sys_name"
                
                # CASE для category_sys_name
                category_sys_cases = []
                for part, full in category_parts_mapping.items():
                    category_sys_cases.append(f"WHEN c.sys_name = '{part}' THEN '{full}'")
                for single in category_single_items:
                    category_sys_cases.append(f"WHEN c.sys_name = '{single}' THEN '{single}'")
                
                if category_sys_cases:
                    category_sys_expr = "CASE " + " ".join(category_sys_cases) + f" ELSE c.sys_name END"
                else:
                    category_sys_expr = "c.sys_name"
                
                # Текстовые выражения
                option_text_expr = build_case_expr(option_texts, option_sys_expr, "po.property_option_text")
                
                category_text_cases = []
                for part, full in category_parts_mapping.items():
                    display_text = category_texts.get(full, full)
                    category_text_cases.append(f"WHEN c.sys_name = '{part}' THEN '{display_text}'")
                for single in category_single_items:
                    category_text_cases.append(f"WHEN c.sys_name = '{single}' THEN c.category_name")
                
                if category_text_cases:
                    category_text_expr = "CASE " + " ".join(category_text_cases) + f" ELSE c.category_name END"
                else:
                    category_text_expr = "c.category_name"
                
                select = f"""
                SELECT
                    p.property_sys_name,
                    p.property_text,
                    {category_sys_expr} AS category_sys_name,
                    {category_text_expr} AS category_text,
                    {option_sys_expr} AS option_sys_name,
                    {option_text_expr} AS option_text,
                    w.weight AS weight,
                    a.resp_id AS resp_id,
                    a.project_id AS project_id
                FROM relevant_answers a
                JOIN weight w ON a.resp_id = w.resp_id AND w.project_id = a.project_id
                JOIN property p ON a.property_id = p.property_id
                JOIN property_option po ON a.property_option_id = po.property_option_id
                JOIN category c ON a.category_id = c.category_id
                WHERE p.property_sys_name = '{property_sys_name}'
                AND po.property_option_sys_name IN ('{all_option_parts}')
                AND c.sys_name IN ('{all_category_parts}')
                AND a.resp_id IN (SELECT resp_id FROM qualified_resp)
                """
                selects.append(select)
                
            else:  # brand
                property_sys_name, option_sys_names, brand_sys_names = item[:3]
                option_text_param = item[3] if len(item) == 4 else None
                
                # Маппинг для опций
                option_parts_mapping = {}
                option_single_items = []
                option_texts = {}  # только для составных опций
                
                for opt in option_sys_names:
                    if " OR " in opt:
                        # Составной элемент - может переопределяться
                        if len(option_sys_names) == 1:
                            if option_text_param:
                                option_texts[opt] = option_text_param
                            else:
                                option_texts[opt] = opt
                        for opt_part in opt.split(" OR "):
                            option_parts_mapping[opt_part] = opt
                    else:
                        # Обычный элемент - НЕ переопределяем
                        option_single_items.append(opt)
                
                # Маппинг для брендов
                brand_parts_mapping = {}
                brand_single_items = []
                brand_texts = {}  # для brand_text (может переопределяться)
                
                for brand in brand_sys_names:
                    if " OR " in brand:
                        # Составной бренд
                        if option_text_param and len(brand_sys_names) == 1:
                            brand_texts[brand] = option_text_param
                        else:
                            brand_texts[brand] = brand
                        for brand_part in brand.split(" OR "):
                            brand_parts_mapping[brand_part] = brand
                    else:
                        # Обычный бренд - НЕ переопределяем текст
                        brand_single_items.append(brand)
                
                # Формируем IN списки
                in_option_parts = []
                in_option_parts.extend(option_parts_mapping.keys())
                in_option_parts.extend(option_single_items)
                all_option_parts = "', '".join(in_option_parts)
                
                in_brand_parts = []
                in_brand_parts.extend(brand_parts_mapping.keys())
                in_brand_parts.extend(brand_single_items)
                all_brand_parts = "', '".join(in_brand_parts)
                
                # CASE для option_sys_name
                option_cases = []
                for part, full in option_parts_mapping.items():
                    option_cases.append(f"WHEN po.property_option_sys_name = '{part}' THEN '{full}'")
                for single in option_single_items:
                    option_cases.append(f"WHEN po.property_option_sys_name = '{single}' THEN '{single}'")
                
                if option_cases:
                    option_sys_expr = "CASE " + " ".join(option_cases) + f" ELSE po.property_option_sys_name END"
                else:
                    option_sys_expr = "po.property_option_sys_name"
                
                # CASE для brand_sys_name
                brand_sys_cases = []
                for part, full in brand_parts_mapping.items():
                    brand_sys_cases.append(f"WHEN b.sys_name = '{part}' THEN '{full}'")
                for single in brand_single_items:
                    brand_sys_cases.append(f"WHEN b.sys_name = '{single}' THEN '{single}'")
                
                if brand_sys_cases:
                    brand_sys_expr = "CASE " + " ".join(brand_sys_cases) + f" ELSE b.sys_name END"
                else:
                    brand_sys_expr = "b.sys_name"
                
                # Текстовые выражения
                option_text_expr = build_case_expr(option_texts, option_sys_expr, "po.property_option_text")
                
                brand_text_cases = []
                for part, full in brand_parts_mapping.items():
                    display_text = brand_texts.get(full, full)
                    brand_text_cases.append(f"WHEN b.sys_name = '{part}' THEN '{display_text}'")
                for single in brand_single_items:
                    brand_text_cases.append(f"WHEN b.sys_name = '{single}' THEN b.brand_name")
                
                if brand_text_cases:
                    brand_text_expr = "CASE " + " ".join(brand_text_cases) + f" ELSE b.brand_name END"
                else:
                    brand_text_expr = "b.brand_name"
                
                select = f"""
                SELECT
                    p.property_sys_name,
                    p.property_text,
                    {brand_sys_expr} AS brand_sys_name,
                    {brand_text_expr} AS brand_text,
                    {option_sys_expr} AS option_sys_name,
                    {option_text_expr} AS option_text,
                    w.weight AS weight,
                    a.resp_id AS resp_id,
                    a.project_id AS project_id
                FROM relevant_answers a
                JOIN weight w ON a.resp_id = w.resp_id AND w.project_id = a.project_id
                JOIN property p ON a.property_id = p.property_id
                JOIN property_option po ON a.property_option_id = po.property_option_id
                JOIN brand b ON a.brand_id = b.brand_id
                WHERE p.property_sys_name = '{property_sys_name}'
                AND po.property_option_sys_name IN ('{all_option_parts}')
                AND b.sys_name IN ('{all_brand_parts}')
                AND a.resp_id IN (SELECT resp_id FROM qualified_resp)
                """
                selects.append(select)
        
        # Объединяем все SELECT через UNION ALL
        union_select = " UNION ALL ".join(selects)
        
        # Формируем финальный запрос с агрегацией
        if dimension_type == 'property':
            group_by_fields = "property_sys_name, property_text, option_sys_name, option_text"
            select_fields = """
                property_sys_name,
                property_text,
                option_sys_name,
                option_text,
                ROUND(SUM(weight) / {num_projects}, 1) AS universe,
                COUNT(*) AS sample
            """
            order_by = "property_text DESC, option_text ASC"
        elif dimension_type == 'category':
            group_by_fields = "property_sys_name, property_text, category_sys_name, category_text, option_sys_name, option_text"
            select_fields = """
                property_sys_name,
                property_text,
                category_sys_name,
                category_text,
                option_sys_name,
                option_text,
                ROUND(SUM(weight) / {num_projects}, 1) AS universe,
                COUNT(*) AS sample
            """
            order_by = "property_text DESC, category_text DESC, option_text ASC"
        else:  # brand
            group_by_fields = "property_sys_name, property_text, brand_sys_name, brand_text, option_sys_name, option_text"
            select_fields = """
                property_sys_name,
                property_text,
                brand_sys_name,
                brand_text,
                option_sys_name,
                option_text,
                ROUND(SUM(weight) / {num_projects}, 1) AS universe,
                COUNT(*) AS sample
            """
            order_by = "property_text DESC, brand_text DESC, option_text ASC"
        
        final_query = f"""
        {base_ctes}
        SELECT
            {select_fields.format(num_projects=num_projects)}
        FROM (
            SELECT DISTINCT
                {group_by_fields},
                weight,
                resp_id,
                project_id
            FROM ({union_select}) combined
        ) t
        GROUP BY {group_by_fields}
        ORDER BY {order_by}
        """
        
        return self._execute_query(final_query, log_sql)

    def calc_project_property_universe(
        self,
        project_ids: list[int],
        properties: list[tuple],
        demo: list | None = None,
        log_sql: bool = False,
    ) -> pd.DataFrame:
        """Calculate universe distribution for list of properties.
    
        Args:
            properties: List of tuples in format:
                - (property_sys_name, option_sys_names) - option_text will be None
                - (property_sys_name, option_sys_names, option_text) - custom option_text for this property
        """
        items = []
        for prop in properties:
            # Проверяем длину элемента
            if len(prop) == 3:
                # Если в кортеже 3 элемента - используем свой option_text
                property_sys_name, option_sys_names, prop_option_text = prop
                # Если передан глобальный option_text, используем его только если нет своего
                final_option_text = prop_option_text
            else:
                # Если 2 элемента - берем из глобального
                property_sys_name, option_sys_names = prop
                final_option_text = None
            
            items.append((property_sys_name, option_sys_names, final_option_text))
        
        return self._calc_universe(
            project_ids=project_ids,
            dimension_type='property',
            items=items,
            demo=demo,
            log_sql=log_sql
        )
    
    def calc_project_category_universe(
        self,
        project_ids: list[int],
        properties: list[tuple],
        demo: list | None = None,
        log_sql: bool = False,
    ) -> pd.DataFrame:
        """Calculate universe distribution for list of properties."""
        items = []
        for prop in properties:
            # Проверяем длину элемента
            if len(prop) == 4:
                # Если в кортеже 4 элемента - используем свой option_text
                property_sys_name, option_sys_names, categories, prop_option_text = prop
                # Если передан глобальный option_text, используем его только если нет своего
                final_option_text = prop_option_text
            else:
                # Если 3 элемента - задаем None
                property_sys_name, option_sys_names, categories = prop
                final_option_text = None
            
            items.append((property_sys_name, option_sys_names, categories, final_option_text))
        
        return self._calc_universe(
            project_ids=project_ids,
            dimension_type='category',
            items=items,
            demo=demo,
            log_sql=log_sql
        )
        
    
    def calc_project_brand_universe(
        self,
        project_ids: list[int],
        properties: list[tuple],
        option_text: str | None = None,
        demo: list | None = None,
        log_sql: bool = False,
    ) -> pd.DataFrame:
        """Calculate universe distribution for list of properties."""
        items = []
        for prop in properties:
            # Проверяем длину элемента
            if len(prop) == 4:
                # Если в кортеже 4 элемента - используем свой option_text
                property_sys_name, option_sys_names, brands, prop_option_text = prop
                # Если передан глобальный option_text, используем его только если нет своего
                final_option_text = prop_option_text
            else:
                # Если 3 элемента - задаем None
                property_sys_name, option_sys_names, brands = prop
                final_option_text = None
            
            items.append((property_sys_name, option_sys_names, brands, final_option_text))
        
        return self._calc_universe(
            project_ids=project_ids,
            dimension_type='brand',
            items=items,
            demo=demo,
            log_sql=log_sql
        )
        

    def _build_demo_filter_ctes(self, property_option_filter: str, demo: list | None) -> str:
        """Build common table expressions for demo filtering."""
        filter_meta = f"""
            filter_meta AS (
                SELECT COUNT(DISTINCT property_id) AS required_count
                FROM property 
                JOIN property_option USING (property_id)
                {property_option_filter}
            ),
            filter_options AS (
                SELECT DISTINCT property_option_id, property_id
                FROM property 
                JOIN property_option USING (property_id)
                {property_option_filter}
            ),"""
        
        return filter_meta if demo else ""

    def _build_qualified_resp_cte(self, demo: list | None) -> str:
        """Build qualified respondents CTE."""
        if demo:
            return """
            qualified_resp AS (
                SELECT DISTINCT ra.resp_id
                FROM relevant_answers ra
                JOIN filter_options fo ON ra.property_option_id = fo.property_option_id
                GROUP BY resp_id
                HAVING COUNT(DISTINCT fo.property_id) = (SELECT required_count FROM filter_meta)
            )"""
        return """
            qualified_resp AS (
                SELECT DISTINCT resp_id
                FROM relevant_answers
            )"""


    def calc_sample(
        self,
        project_ids: list[int],
        demo: list | None = None,
        log_sql: bool = False,
    ) -> int:
        """Calculate sample size (distinct respondents) for profile."""
        property_option_filter = self._build_property_option_filter(demo)
        
        demo_ctes = self._build_demo_filter_ctes(property_option_filter, demo)
        qualified_resp_cte = self._build_qualified_resp_cte(demo)
        
        all_project_ids = ", ".join([str(i) for i in project_ids])

        query = f"""
            WITH {demo_ctes} 
            relevant_answers AS (
                SELECT DISTINCT resp_id, property_option_id
                FROM (
                SELECT * FROM answer a
                WHERE a.project_id IN ({all_project_ids})  
                    OR a.project_id IN (
                        SELECT parent_profile_id 
                        FROM projects 
                        WHERE project_id IN ({all_project_ids}) 
                    )
                UNION ALL
                SELECT *
                FROM boost_answer b
                WHERE b.project_id IN ({all_project_ids}) )              
            ),
            {qualified_resp_cte}
            SELECT COUNT(*) AS sample
            FROM qualified_resp qr 
            JOIN weight w ON qr.resp_id = w.resp_id
            WHERE w.project_id IN ({all_project_ids}) 
        """

        df = self._execute_query(query, log_sql)
        return int(df.iloc[0, 0])


    def calc_universe(
        self,
        project_ids: list[int],
        demo: list | None = None,
        log_sql: bool = False,
    ) -> float:
        """Calculate total universe weight for profile."""
        property_option_filter = self._build_property_option_filter(demo)
        
        demo_ctes = self._build_demo_filter_ctes(property_option_filter, demo)
        qualified_resp_cte = self._build_qualified_resp_cte(demo)
        
        all_project_ids = ", ".join([str(i) for i in project_ids])

        query = f"""
            WITH {demo_ctes}
            relevant_answers AS (
                SELECT DISTINCT a.resp_id, a.property_option_id
                FROM answer a
                WHERE a.project_id IN ({all_project_ids})  
                    OR a.project_id IN (
                        SELECT parent_profile_id 
                        FROM projects 
                        WHERE project_id IN ({all_project_ids}) 
                    )
                UNION ALL
                SELECT DISTINCT b.resp_id, b.property_option_id
                FROM boost_answer b
                WHERE b.project_id IN ({all_project_ids})
            ),
            {qualified_resp_cte}
            SELECT SUM(w.weight) / {len(project_ids)} AS universe
            FROM qualified_resp qr
            JOIN weight w ON qr.resp_id = w.resp_id
            WHERE w.project_id IN ({all_project_ids}) 
        """

        df = self._execute_query(query, log_sql)
        return round(float(df.iloc[0, 0]), 1)

    
    def calc_universe_property_by_brand(
        self,
        project_ids: list[int],
        properties: list[tuple],
        option_text: str = None,
        demo: list | None = None,
        log_sql: bool = False,
    ) -> float:
        """Calculate universe for property and """
        property_option_filter = self._build_property_option_filter(demo)
        
        all_project_ids = ", ".join([str(i) for i in project_ids])
        
        demo_ctes = self._build_demo_filter_ctes(property_option_filter, demo)
        qualified_resp_cte = self._build_qualified_resp_cte(demo)
        
        data_frames = []
        for property_sys_name, option_sys_names, brands, option_text in properties:           
            
            split_items = []
            for item in brands:
                split_items.extend(item.split(" OR "))
            all_brand_sys_names = "', '".join(split_items)
            
            split_items = []
            for item in option_sys_names:
                split_items.extend(item.split(" OR "))
            all_option_sys_names = "', '".join(split_items)
            
            if option_text and len(brands) == 1:
                modified_brand_sys_name = f"'{brands[0]}'"
                modified_brand_text = f"'{option_text}'"
            else:
                modified_brand_sys_name = "b.sys_name"
                modified_brand_text = "b.brand_name"
            
            query = f"""
            WITH {demo_ctes} 
            relevant_answers AS (
                SELECT * 
                FROM answer a
                WHERE a.project_id IN ({all_project_ids})  
                    OR a.project_id IN (
                        SELECT parent_profile_id 
                        FROM projects 
                        WHERE project_id IN ({all_project_ids})  
                    )
                UNION ALL
                SELECT *
                FROM boost_answer b
                WHERE b.project_id IN ({all_project_ids}) 
            ),
            {qualified_resp_cte}
            SELECT
                property_sys_name,
                property_text,
                brand_sys_name,
                brand_text,
                ROUND(SUM(weight), 1) AS universe,
                COUNT(*) AS sample
            FROM (
            SELECT
                DISTINCT 
                p.property_sys_name AS property_sys_name,
                p.property_text AS property_text,
                {modified_brand_sys_name} AS brand_sys_name,
                {modified_brand_text} AS brand_text,
                w.weight AS weight,
                a.resp_id AS resp_id
            FROM relevant_answers a
            JOIN weight w ON a.resp_id = w.resp_id AND w.project_id = a.project_id
            JOIN property p ON a.property_id = p.property_id
            JOIN property_option po ON a.property_option_id = po.property_option_id
            JOIN brand b ON a.brand_id = b.brand_id
            WHERE p.property_sys_name = '{property_sys_name}'
              AND po.property_option_sys_name IN ('{all_option_sys_names}')
              AND b.sys_name IN ('{all_brand_sys_names}')
              AND a.resp_id IN (SELECT resp_id FROM qualified_resp)) 
            GROUP BY property_sys_name, property_text, brand_sys_name, brand_text
            ORDER BY property_text DESC, brand_text DESC
            """
            df = self._execute_query(query, log_sql)
            data_frames.append(df)            
        return pd.concat(data_frames, ignore_index=True)

    
    def calc_universe_property_by_category(
        self,
        project_ids: list[int],
        properties: list[tuple],
        option_text: str = None,
        demo: list | None = None,
        log_sql: bool = False,
    ) -> float:
        """Calculate universe for property and """
        property_option_filter = self._build_property_option_filter(demo)
        
        all_project_ids = ", ".join([str(i) for i in project_ids])
        
        demo_ctes = self._build_demo_filter_ctes(property_option_filter, demo)
        qualified_resp_cte = self._build_qualified_resp_cte(demo)
        
        data_frames = []
        for property_sys_name, option_sys_names, categories, option_text in properties:           
            
            split_items = []
            for item in categories:
                split_items.extend(item.split(" OR "))
            all_category_sys_names = "', '".join(split_items)
            
            split_items = []
            for item in option_sys_names:
                split_items.extend(item.split(" OR "))
            all_option_sys_names = "', '".join(split_items)
            
            if option_text and len(categories) == 1:
                modified_category_sys_name = f"'{categories[0]}'"
                modified_category_text = f"'{option_text}'"
            else:
                modified_category_sys_name = "c.sys_name"
                modified_category_text = "c.category_name"
            
            query = f"""
            WITH {demo_ctes} 
            relevant_answers AS (
                SELECT * 
                FROM answer a
                WHERE a.project_id IN ({all_project_ids})  
                    OR a.project_id IN (
                        SELECT parent_profile_id 
                        FROM projects 
                        WHERE project_id IN ({all_project_ids})  
                    )
                UNION ALL
                SELECT *
                FROM boost_answer b
                WHERE b.project_id IN ({all_project_ids}) 
            ),
            {qualified_resp_cte}
            SELECT
                property_sys_name,
                property_text,
                category_sys_name,
                category_text,
                ROUND(SUM(weight), 1) AS universe,
                COUNT(*) AS sample
            FROM (
            SELECT
                DISTINCT 
                p.property_sys_name AS property_sys_name,
                p.property_text AS property_text,
                {modified_category_sys_name} AS category_sys_name,
                {modified_category_text} AS category_text,
                w.weight AS weight,
                a.resp_id AS resp_id
            FROM relevant_answers a
            JOIN weight w ON a.resp_id = w.resp_id AND w.project_id = a.project_id
            JOIN property p ON a.property_id = p.property_id
            JOIN property_option po ON a.property_option_id = po.property_option_id
            JOIN category c ON a.category_id = c.category_id
            WHERE p.property_sys_name = '{property_sys_name}'
              AND po.property_option_sys_name IN ('{all_option_sys_names}')
              AND c.sys_name IN ('{all_category_sys_names}')
              AND a.resp_id IN (SELECT resp_id FROM qualified_resp)) 
            GROUP BY property_sys_name, property_text, category_sys_name, category_text
            ORDER BY property_text DESC, category_text DESC
            """
            df = self._execute_query(query, log_sql)
            data_frames.append(df)            
        return pd.concat(data_frames, ignore_index=True)

    
    def calc_universe_property(
        self,
        project_ids: list[int],
        properties: list[tuple],
        demo: list | None = None,
        option_text: str = None,
        log_sql: bool = False,
    ) -> float:
        """Calculate universe for property and """
        property_option_filter = self._build_property_option_filter(demo)
        
        all_project_ids = ", ".join([str(i) for i in project_ids])
        
        demo_ctes = self._build_demo_filter_ctes(property_option_filter, demo)
        qualified_resp_cte = self._build_qualified_resp_cte(demo)
        
        data_frames = []
        for property_sys_name, option_sys_names, option_text in properties:  
            
            split_items = []
            for item in option_sys_names:
                split_items.extend(item.split(" OR "))
            all_option_sys_names = "', '".join(split_items) 
            
            query = f"""
            WITH {demo_ctes} 
            relevant_answers AS (
                SELECT * 
                FROM answer a
                WHERE a.project_id IN ({all_project_ids})  
                    OR a.project_id IN (
                        SELECT parent_profile_id 
                        FROM projects 
                        WHERE project_id IN ({all_project_ids})  
                    )
                UNION ALL
                SELECT *
                FROM boost_answer b
                WHERE b.project_id IN ({all_project_ids}) 
            ),
            {qualified_resp_cte}
            SELECT
                property_sys_name,
                property_text,
                ROUND(SUM(weight), 1) AS universe,
                COUNT(*) AS sample
            FROM (
            SELECT
                DISTINCT
                p.property_sys_name AS property_sys_name,
                p.property_text AS property_text,
                w.weight AS weight,
                a.resp_id AS resp_id
            FROM relevant_answers a
            JOIN weight w ON a.resp_id = w.resp_id AND w.project_id = a.project_id
            JOIN property p ON a.property_id = p.property_id
            JOIN property_option po ON a.property_option_id = po.property_option_id
            WHERE p.property_sys_name = '{property_sys_name}'
              AND po.property_option_sys_name IN ('{all_option_sys_names}')
              AND a.resp_id IN (SELECT resp_id FROM qualified_resp)) 
            GROUP BY property_sys_name, property_text
            ORDER BY property_text DESC
            """
            df = self._execute_query(query, log_sql)
            data_frames.append(df)            
        return pd.concat(data_frames, ignore_index=True)
    
    
    def find_property(self, text: str = None, sys_name: str = None) -> pd.DataFrame:
        df = self._execute_query(query="SELECT * FROM property")
        mask = True

        if text:
            mask &= df["property_text"].str.contains(text, regex=True)

        if sys_name:
            mask &= df["property_sys_name"].str.contains(sys_name, regex=True)

        return df[mask]

    def find_property_options(
        self,
        text: str = None,
        sys_name: str = None,
        property_sys_name: str = None
    ) -> pd.DataFrame:
        query = """
            SELECT *
            FROM property_option po
            JOIN property p ON po.property_id = p.property_id
        """
        df = self._execute_query(query=query)
        mask = True

        if text:
            mask &= df["property_option_text"].str.contains(text, regex=True)

        if sys_name:
            mask &= df["property_option_sys_name"].str.contains(sys_name, regex=True)

        if property_sys_name:
            mask &= df["property_sys_name"].str.contains(property_sys_name, regex=True)

        return df[mask]
    
    def find_projects(
        self,
        project_name: str = None,
        project_name_eng: str = None,
        wave_name: str = None,
        wave_begin: str = None,
        wave_end: str = None,
        category_name: str = None,
        category_name_eng: str = None,
        category_sys_name: str = None
    ) -> pd.DataFrame:
        query = """
            SELECT p.*,
            w.dt_begin, w.dt_end, w.wave_name, w.wave_name_eng,	w.wave_type_id,
            c.category_name, c.category_name_eng, c.description, c.description_eng, 
            c.sys_name as category_sys_name
            FROM projects p
            JOIN wave w ON p.wave_id = w.wave_id
            JOIN category c ON p.category_id = c.category_id
        """
        df = self._execute_query(query=query)
        mask = pd.Series([True] * len(df), index=df.index)

        if project_name:
            mask &= df["project_name"].str.contains(project_name, regex=True)
            
        if project_name_eng:
            mask &= df["project_name_eng"].str.contains(project_name_eng, regex=True)

        if wave_name:
            mask &= df["wave_name"].str.contains(wave_name, regex=True)
        
        if wave_begin:
            mask &= (df["dt_begin"] == pd.to_datetime(wave_begin))
        
        if wave_end:
            mask &= (df["dt_end"] == pd.to_datetime(wave_end))

        if category_name:
            mask &= df["category_name"].str.contains(category_name, regex=True)
        
        if category_name_eng:
            mask &= df["category_name_eng"].str.contains(category_name_eng, regex=True)
            
        if category_sys_name:
            mask &= df["category_sys_name"].str.contains(category_sys_name, regex=True)

        return df[mask]
    
    def find_brands(
        self,
        brand_name: str = None,
        brand_name_eng: str = None,
        brand_sys_name: str = None,
        category_name: str = None,
        category_name_eng: str = None,
        category_sys_name: str = None
    ) -> pd.DataFrame:
        query = """
            SELECT b.brand_name, b.brand_name_eng, b.sys_name as brand_sys_name,
            c.category_name, c.category_name_eng, c.description, c.description_eng, 
            c.sys_name as category_sys_name
            FROM brand_category bc
            JOIN brand b ON bc.brand_id = b.brand_id
            JOIN category c ON bc.category_id = c.category_id
        """
        df = self._execute_query(query=query)
        mask = pd.Series([True] * len(df), index=df.index)

        if brand_name:
            mask &= df["brand_name"].str.contains(brand_name, regex=True)
            
        if brand_name_eng:
            mask &= df["brand_name_eng"].str.contains(brand_name_eng, regex=True)

        if brand_sys_name:
            mask &= df["brand_sys_name"].str.contains(brand_sys_name, regex=True)

        if category_name:
            mask &= df["category_name"].str.contains(category_name, regex=True)
        
        if category_name_eng:
            mask &= df["category_name_eng"].str.contains(category_name_eng, regex=True)
            
        if category_sys_name:
            mask &= df["category_sys_name"].str.contains(category_sys_name, regex=True)

        return df[mask]
    
    def find_category_brand_property(
        self,
        category_name: str = None,
        category_name_eng: str = None,
        category_sys_name: str = None,
        brand_name: str = None,
        brand_name_eng: str = None,
        brand_sys_name: str = None,
        property_name: str = None,
        property_sys_name: str = None
    ) -> pd.DataFrame:
        query = """
            WITH full_answers AS (
                SELECT DISTINCT category_id, brand_id, property_id 
                FROM answer
                UNION ALL
                SELECT DISTINCT category_id, brand_id, property_id 
                FROM boost_answer
            ),
            enriched_answers AS (
                SELECT 
                    CASE 
                        WHEN a.category_id IS NULL AND a.brand_id IS NOT NULL 
                        THEN COALESCE(CAST(cb.category_id AS VARCHAR), a.category_id)
                        ELSE a.category_id
                    END AS category_id,
                    a.brand_id,
                    a.property_id,
                    CASE 
                        WHEN a.category_id IS NULL AND a.brand_id IS NOT NULL AND cb.category_id IS NOT NULL
                        THEN TRUE
                        ELSE FALSE
                    END AS is_filled_category_from_dict
                FROM full_answers a
                LEFT JOIN brand_category cb ON a.brand_id = cb.brand_id
            )
            SELECT 
                c.category_name, 
                c.category_name_eng, 
                c.sys_name AS category_sys_name, 
                b.brand_name, 
                b.brand_name_eng, 
                b.sys_name AS brand_sys_name,
                p.property_text AS property_name, 
                p.property_sys_name,
                ea.is_filled_category_from_dict
            FROM enriched_answers ea
            LEFT JOIN category c ON ea.category_id = c.category_id
            LEFT JOIN brand b ON ea.brand_id = b.brand_id
            LEFT JOIN property p ON ea.property_id = p.property_id
        """
        df = self._execute_query(query=query)
        mask = pd.Series([True] * len(df), index=df.index)

        if brand_name:
            mask &= df["brand_name"].str.contains(brand_name, regex=True)
            
        if brand_name_eng:
            mask &= df["brand_name_eng"].str.contains(brand_name_eng, regex=True)

        if brand_sys_name:
            mask &= df["brand_sys_name"].str.contains(brand_sys_name, regex=True)

        if category_name:
            mask &= df["category_name"].str.contains(category_name, regex=True)
        
        if category_name_eng:
            mask &= df["category_name_eng"].str.contains(category_name_eng, regex=True)
            
        if category_sys_name:
            mask &= df["category_sys_name"].str.contains(category_sys_name, regex=True)
            
        if property_name:
            mask &= df["property_name"].str.contains(property_name, regex=True)
            
        if property_sys_name:
            mask &= df["property_sys_name"].str.contains(property_sys_name, regex=True)

        return df[mask]
    
    
    def calc_crosstab_property_universe(
        self,
        project_id: int,
        property_sys_names_left: list[str],
        property_sys_name_up: str,
        demo: list | None = None,
        log_sql: bool = False,
    ) -> pd.DataFrame:
        """Calculate property universe distribution for profile."""
        # получить возможные значения свойства и отсортировать их по полю property_option_order 
        SQL_PROPERTY_OPTION_TEMPLATE = f'''
        SELECT 
            property_option_text
        FROM property_option 
        WHERE property_id IN (SELECT property_id FROM property WHERE property_sys_name = '{property_sys_name_up}')
        ORDER BY property_option_order
        '''
        # значения свойства сверху (нужно для PIVOT)
        property_up_values = self._execute_query(query=SQL_PROPERTY_OPTION_TEMPLATE, log_sql=log_sql)['property_option_text'].to_list()
        
        property_option_filter = self._build_property_option_filter(demo)
        
        demo_ctes = self._build_demo_filter_ctes(property_option_filter, demo)
        qualified_resp_cte = self._build_qualified_resp_cte(demo)

        query = f"""
            WITH {demo_ctes}
            relevant_answers AS (
                SELECT * 
                FROM answer a
                WHERE a.project_id = {project_id} 
                    OR a.project_id IN (
                        SELECT parent_profile_id 
                        FROM projects 
                        WHERE project_id = {project_id} 
                    )
                UNION ALL
                SELECT *
                FROM boost_answer b
                WHERE b.project_id = {project_id} 
            ),
            {qualified_resp_cte}
            SELECT *
            FROM (
            SELECT 
                p1.property_sys_name AS property_sys_name,
                p1.property_text AS property_text,
                po1.property_option_sys_name AS option_sys_name,
                po1.property_option_text AS option_text,
                po2.property_option_text AS up,
                weight
            FROM answer a
            JOIN weight w ON a.resp_id = w.resp_id AND w.project_id = a.project_id
            JOIN property     p1 ON a.property_id = p1.property_id
            JOIN property_option po1 ON a.property_option_id = po1.property_option_id
            JOIN answer a2 ON a.resp_id = a2.resp_id AND a2.project_id = a.project_id
            JOIN property     p2 ON a2.property_id = p2.property_id AND p2.property_sys_name = '{property_sys_name_up}'
            JOIN property_option po2 ON a2.property_option_id = po2.property_option_id
            WHERE a.project_id = {project_id}  
                AND p1.property_sys_name IN ({', '.join([f"'{item}'" for item in property_sys_names_left])})
                AND a.resp_id IN (SELECT resp_id FROM qualified_resp) 
            ) src
            PIVOT (
            ROUND(SUM(weight), 1) 
            FOR up IN ({', '.join([f"'{item}'" for item in property_up_values])})
            )
            ORDER BY property_text DESC, option_text ASC
        """
        return self._execute_query(query, log_sql)
    
    def prepare_brand_calc_sign_model(
        self,
        project_ids: list[int],
        property_sys_name: str,
        brand_sys_name: str,
        option_sys_name: str,
        demo: list | None = None,
        log_sql: bool = False,
    ) -> pd.DataFrame:
        """Calculate brand universe distribution for profile."""
        property_option_filter = self._build_property_option_filter(demo)
        
        demo_ctes = self._build_demo_filter_ctes(property_option_filter, demo)
        qualified_resp_cte = self._build_qualified_resp_cte(demo)
        
        all_project_ids = ", ".join([str(i) for i in project_ids])

        query = f"""
            WITH {demo_ctes}
            relevant_answers AS (
                SELECT * 
                FROM answer a
                WHERE a.project_id IN ({all_project_ids})  
                    OR a.project_id IN (
                        SELECT parent_profile_id 
                        FROM projects 
                        WHERE project_id IN ({all_project_ids})  
                    )
                UNION ALL
                SELECT *
                FROM boost_answer b
                WHERE b.project_id IN ({all_project_ids}) 
            ),
            {qualified_resp_cte}
            SELECT 
            project_name, resp_id, weight,
            COALESCE(answer::int, 0) AS response 
            FROM (
            SELECT *
            FROM answers a
            WHERE project_id IN ({all_project_ids})
            AND property_id IN (SELECT property_id FROM property WHERE property_sys_name = '{property_sys_name}') 
            AND property_option_id IN (
                SELECT property_option_id FROM property_option 
                WHERE property_option_sys_name = '{option_sys_name}'
                AND property_id IN (SELECT property_id FROM property WHERE property_sys_name = '{property_sys_name}')) 
            AND brand_id IN (SELECT brand_id FROM brand WHERE sys_name = '{brand_sys_name}')
            AND a.resp_id IN (SELECT resp_id FROM qualified_resp) )
            RIGHT JOIN (SELECT *
            FROM weight
            WHERE project_id IN ({all_project_ids}))
            USING (project_id, resp_id)
            INNER JOIN projects
            USING (project_id)
        """
        return self._execute_query(query, log_sql)
    
    def prepare_property_calc_sign_model(
        self,
        project_ids: list[int],
        property_sys_name: str,
        option_sys_name: str,
        demo: list | None = None,
        log_sql: bool = False,
    ) -> pd.DataFrame:
        """Calculate brand universe distribution for profile."""
        property_option_filter = self._build_property_option_filter(demo)
        
        demo_ctes = self._build_demo_filter_ctes(property_option_filter, demo)
        qualified_resp_cte = self._build_qualified_resp_cte(demo)
        
        all_project_ids = ", ".join([str(i) for i in project_ids])

        query = f"""
            WITH {demo_ctes}
            relevant_answers AS (
                SELECT * 
                FROM answer a
                WHERE a.project_id IN ({all_project_ids})  
                    OR a.project_id IN (
                        SELECT parent_profile_id 
                        FROM projects 
                        WHERE project_id IN ({all_project_ids})  
                    )
                UNION ALL
                SELECT *
                FROM boost_answer b
                WHERE b.project_id IN ({all_project_ids}) 
            ),
            {qualified_resp_cte}
            SELECT 
            project_name, resp_id, weight,
            COALESCE(answer::int, 0) AS response 
            FROM (
            SELECT *
            FROM answers a
            WHERE project_id IN ({all_project_ids})
            AND property_id IN (SELECT property_id FROM property WHERE property_sys_name = '{property_sys_name}') 
            AND property_option_id IN (
                SELECT property_option_id FROM property_option 
                WHERE property_option_sys_name = '{option_sys_name}'
                AND property_id IN (SELECT property_id FROM property WHERE property_sys_name = '{property_sys_name}')) 
            AND a.resp_id IN (SELECT resp_id FROM qualified_resp) )
            RIGHT JOIN (SELECT *
            FROM weight
            WHERE project_id IN ({all_project_ids}))
            USING (project_id, resp_id)
            INNER JOIN projects
            USING (project_id)
        """
        return self._execute_query(query, log_sql)
    
    def find_project_property(
            self,
            project_id: int,
            property_name: str = None,
            property_sys_name: str = None
    ) -> pd.DataFrame:
        query = f"""
            WITH full_answers AS (
                SELECT DISTINCT project_id, property_id 
                FROM answer
                UNION ALL
                SELECT DISTINCT project_id, property_id 
                FROM boost_answer
            ),
            filtered_answers AS (
                SELECT * 
                FROM full_answers
                WHERE project_id={str(project_id)}
            )
            SELECT 
                p.property_text AS property_name, 
                p.property_sys_name
            FROM filtered_answers fa
            LEFT JOIN property p ON fa.property_id = p.property_id
        """
        df = self._execute_query(query=query)
        mask = pd.Series([True] * len(df), index=df.index)

        if property_name:
            mask &= df["property_name"].str.contains(property_name, regex=True)

        if property_sys_name:
            mask &= df["property_sys_name"].str.contains(property_sys_name, regex=True)
        return df[mask]
    