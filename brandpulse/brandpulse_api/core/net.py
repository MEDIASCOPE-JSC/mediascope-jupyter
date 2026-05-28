import requests
import datetime
import os
from typing import Optional, Dict, Any
from . import errors
from . import utils


class MediascopeApiNetwork:
    """Клиент для работы с Mediascope API."""
    
    DEFAULT_SETTINGS_FILENAME = 'settings.json'

    def __init__(
        self,
        settings_filename: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        root_url: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        keycloak_url: Optional[str] = None,
        *args,
        **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        
        proxy_server: Optional[str] = None
        
        if all(param is not None for param in [username, password, root_url, client_id, client_secret, keycloak_url]):
            self.username = username
            self.password = password
            self.root_url = root_url
            self.client_id = client_id
            self.client_secret = client_secret
            self.keycloak_url = keycloak_url
        else:
            if settings_filename is None:
                settings_filename = self.DEFAULT_SETTINGS_FILENAME if os.path.exists(self.DEFAULT_SETTINGS_FILENAME) else None
            
            if settings_filename is None or not os.path.exists(settings_filename):
                raise ValueError('Не указаны настройки для подключения к Mediascope-API')
            
            settings = utils.load_settings(settings_filename)
            self.username, self.password, self.root_url, self.client_id, \
            self.client_secret, self.keycloak_url, proxy_server = settings
        
        if any(param is None for param in [self.username, self.password, self.root_url, 
                                          self.client_id, self.client_secret, self.keycloak_url]):
            raise ValueError('Не указаны настройки для подключения к Mediascope-API')
        
        self.token: Dict[str, Any] = {}
        self._setup_proxies(proxy_server)

    def _setup_proxies(self, proxy_server: Optional[str]) -> None:
        """Настройка прокси."""
        if proxy_server:
            self.proxies = {"https": proxy_server}
            print(f"Подключение через прокси {self.proxies}")
        else:
            self.proxies = {"https": ""}

    def get_token(self, username: str, password: str) -> Dict[str, Any]:
        """
        Получить токен по имени пользователя и паролю.

        Args:
            username: Имя пользователя (login)
            password: Пароль пользователя

        Returns:
            Токен доступа к Mediascope-API

        Raises:
            ValueError: Ошибка авторизации или неверные параметры
        """
        response = requests.post(
            url=self.keycloak_url,
            data={
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'username': username,
                'password': password,
                'grant_type': 'password'
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            proxies=self.proxies
        )
        
        if response.status_code == 200:
            token = response.json()
            token['now'] = datetime.datetime.now()
            return token
        
        self._handle_auth_error(response)
        raise ValueError(f"Неожиданный статус: {response.status_code}")

    def _handle_auth_error(self, response: requests.Response) -> None:
        """Обработка ошибок авторизации."""
        if response.status_code == 401:
            raise ValueError('Ошибка авторизации! '
                           'Неверный логин или пароль. Проверьте settings.json')
        elif response.status_code == 403:
            raise ValueError('Ошибка авторизации! Доступ запрещен.')
        else:
            raise ValueError(f'Status code {response.status_code}: {response.text}')

    def refresh_token(self) -> None:
        """Обновить токен если он истек."""
        if not self.token or 'now' not in self.token:
            self.token = self.get_token(self.username, self.password)
            return
        
        now = datetime.datetime.now()
        token_time = self.token['now']
        expires_in = self.token.get('expires_in', 0)
        
        if (now - token_time).total_seconds() >= expires_in - 60:  # Буфер 60 сек
            self.token = self.get_token(self.username, self.password)

    def send_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None
    ) -> requests.Response:
        """
        Отправляет запрос в Mediascope-API.

        Args:
            method: HTTP метод ('get', 'post', 'delete')
            endpoint: Путь к API endpoint
            data: Данные для POST запроса

        Returns:
            requests.Response: Результат запроса

        Raises:
            ValueError: Неверный HTTP метод или ошибка API
        """
        if method.lower() not in {'get', 'post', 'delete'}:
            raise ValueError(f'Method "{method}" is not supported')
        
        self.refresh_token()
        
        url = self.root_url.rstrip('/') + '/' + endpoint.lstrip('/')
        headers = {
            'Authorization': f'Bearer {self.token["access_token"]}',
            'Content-Type': 'application/json; charset=utf-8'
        }
        
        if method.lower() == 'get':
            response = requests.get(url, headers=headers, proxies=self.proxies)
        elif method.lower() == 'delete':
            response = requests.delete(url, headers=headers, proxies=self.proxies)
        else:  # post
            response = requests.post(
                url, 
                headers=headers, 
                json=data or {},
                proxies=self.proxies
            )
        
        if response.status_code == 200:
            return response
        
        self._raise_error(response)
        return response

    @staticmethod
    def _raise_error(response: requests.Response) -> None:
        """Поднять исключение на основе HTTP статуса."""
        status_code = response.status_code
        message = response.text
        
        error_map = {
            204: ('Нет данных', f'Code: {status_code}, Сообщение: "{message}"'),
            401: ('Не авторизирован', f'Code: {status_code}, Сообщение: "{message}"'),
            403: ('Доступ запрещен', f'Code: {status_code}, Сообщение: "{message}"'),
            400: (errors.HTTP400Error(status_code, message), None),
            429: ('Слишком много запросов', f'Code: {status_code}, Сообщение: "{message}"'),
            404: (errors.HTTP404Error(f'Code: {status_code}, Адрес или задача не найдена: "{message}"'), None),
        }
        
        if status_code in error_map:
            exc_class, exc_msg = error_map[status_code]
            if isinstance(exc_class, type):
                raise exc_class()
            else:
                raise ValueError(exc_msg or str(exc_class))
        
        raise ValueError(f'Ошибка. Code: {status_code}, Сообщение: "{message}"')
