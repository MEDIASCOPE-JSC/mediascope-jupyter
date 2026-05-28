import os
import time
import pandas as pd
import tarfile
from .core import net


class BrandpulseData:
    # Default parameters for saving data
    DEFAULT_DOWNLOADS_DIR = 'packed_data'
    DEFAULT_EXTRACT_DIR = 'unpacked_data'
    DEFAULT_ARCHIVE_FORMAT = '.tar.gz'

    def __init__(
        self,
        settings_filename: str = None,
        username: str = None, 
        passw: str = None,
        root_url: str = None,
        client_id: str = None,
        client_secret: str = None,
        keycloak_url: str = None,
        download_dir: str = DEFAULT_DOWNLOADS_DIR,
        extract_dir: str = DEFAULT_EXTRACT_DIR,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.msapi_network = net.MediascopeApiNetwork(
            settings_filename, username, passw,
            root_url, client_id, client_secret, keycloak_url
        )
        self.download_dir = download_dir
        self.extract_dir = extract_dir

    def download_extract_data(self, endpoint: str, filename: str) -> None:
        """
        Download and extract data archive from the specified endpoint.
        """
        print('Starting data download...')
        start_time = time.perf_counter()

        response = self.msapi_network.send_request('get', endpoint)
        os.makedirs(self.download_dir, exist_ok=True)
        filepath = os.path.join(self.download_dir, filename)

        with open(filepath, 'wb') as f:
            f.write(response.content)

        elapsed = time.perf_counter() - start_time
        minutes, seconds = divmod(elapsed, 60)
        print(f'Data successfully downloaded to {filepath} in {int(minutes)} min {seconds:.3f} sec')

        os.makedirs(self.extract_dir, exist_ok=True)
        with tarfile.open(filepath) as tar:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(path=self.extract_dir, filter=tarfile.data_filter)
            else:
                tar.extractall(path=self.extract_dir)

        print(f'Data successfully extracted to {self.extract_dir}')

    def get_available_projects(self) -> pd.DataFrame:
        """
        Retrieve the list of available projects.
        """
        response = self.msapi_network.send_request('get', '/list')
        return pd.DataFrame(response.json())

    def get_projects(self, project_ids: list) -> None:
        """
        Download and extract data for the specified project IDs.
        """
        archive_name = f'project-{project_ids[0]}{self.DEFAULT_ARCHIVE_FORMAT}'
        endpoint = f"/project?projectIds={','.join(map(str, project_ids))}"
        self.download_extract_data(endpoint, archive_name)

    def get_profile(self, year: int) -> None:
        """
        Download and extract profile data for the specified year.
        """
        archive_name = f'profile-{year}{self.DEFAULT_ARCHIVE_FORMAT}'
        endpoint = f'/profile?year={year}'
        self.download_extract_data(endpoint, archive_name)

    def get_dictionary(self) -> None:
        """
        Download and extract the dictionary data.
        """
        archive_name = f'dictionary{self.DEFAULT_ARCHIVE_FORMAT}'
        endpoint = '/dictionary'
        self.download_extract_data(endpoint, archive_name)

    def get_boost_answer(self, project_ids: list) -> None:
        """
        Download and extract boost answer data for specified project IDs.
        """
        archive_name = f'boost-answer-{project_ids[0]}{self.DEFAULT_ARCHIVE_FORMAT}'
        endpoint = f"/boost_answer?projectIds={','.join(map(str, project_ids))}"
        self.download_extract_data(endpoint, archive_name)
