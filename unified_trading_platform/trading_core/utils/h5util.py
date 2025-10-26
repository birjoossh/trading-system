"""
H5 File Utilities for reading and converting H5 data to DataFrames.
Provides comprehensive functionality for working with H5 files containing market data.
"""

import pandas as pd
import numpy as np
import h5py
from pathlib import Path
from typing import Dict, List, Optional, Union, Any
from datetime import datetime, date
import warnings

class H5DataReader:
    """Utility class for reading and processing H5 files containing market data"""
    
    def __init__(self, h5_file_path: Union[str, Path]):
        """
        Initialize H5 data reader
        
        Args:
            h5_file_path: Path to the H5 file
        """
        self.h5_file_path = Path(h5_file_path)
        if not self.h5_file_path.exists():
            raise FileNotFoundError(f"H5 file not found: {self.h5_file_path}")
        
        self._file = None
        self._groups = None
    
    def __enter__(self):
        """Context manager entry"""
        self._file = h5py.File(self.h5_file_path, 'r')
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if self._file:
            self._file.close()
    
    def get_groups(self) -> List[str]:
        """Get list of all groups in the H5 file"""
        if self._file is None:
            raise RuntimeError("File not opened. Use context manager or call open_file()")
        
        def get_all_groups(name, obj):
            if isinstance(obj, h5py.Group):
                self._groups.append(name)
        
        self._groups = []
        self._file.visititems(get_all_groups)
        return self._groups
    
    def get_datasets(self, group_path: str = '/') -> List[str]:
        """Get list of all datasets in a group"""
        if self._file is None:
            raise RuntimeError("File not opened. Use context manager or call open_file()")
        
        def get_all_datasets(name, obj):
            if isinstance(obj, h5py.Dataset):
                self._datasets.append(name)
        
        self._datasets = []
        if group_path in self._file:
            self._file[group_path].visititems(get_all_datasets)
        return self._datasets
    
    def read_dataset(self, dataset_path: str, as_dataframe: bool = True) -> Union[pd.DataFrame, np.ndarray]:
        """
        Read a dataset from the H5 file
        
        Args:
            dataset_path: Path to the dataset in the H5 file
            as_dataframe: If True, convert to DataFrame, otherwise return numpy array
            
        Returns:
            DataFrame or numpy array
        """
        if self._file is None:
            raise RuntimeError("File not opened. Use context manager or call open_file()")
        
        if dataset_path not in self._file:
            raise KeyError(f"Dataset not found: {dataset_path}")
        
        data = self._file[dataset_path][:]
        
        if as_dataframe:
            return pd.DataFrame(data)
        return data
    
    def read_spot_series(self, symbol: str = "NIFTY") -> pd.DataFrame:
        """
        Read spot price series from H5 file
        
        Args:
            symbol: Symbol to read (default: NIFTY)
            
        Returns:
            DataFrame with timestamp index and price data
        """
        if self._file is None:
            raise RuntimeError("File not opened. Use context manager or call open_file()")
        
        # Common paths for spot data
        possible_paths = [
            f'/spot/{symbol}',
            f'/spot/{symbol.lower()}',
            f'/spot_data/{symbol}',
            f'/underlying/{symbol}',
            f'/cash/{symbol}',
            f'/{symbol}/spot'
        ]
        
        for path in possible_paths:
            if path in self._file:
                try:
                    data = self._file[path][:]
                    if len(data.shape) == 1:
                        # 1D array - assume it's price series
                        df = pd.DataFrame({'price': data})
                        df.index = pd.date_range(start='2024-01-01', periods=len(data), freq='1min')
                    else:
                        # Multi-dimensional - try to parse as OHLCV
                        df = pd.DataFrame(data)
                        if 'timestamp' in df.columns:
                            df['timestamp'] = pd.to_datetime(df['timestamp'])
                            df.set_index('timestamp', inplace=True)
                    return df
                except Exception as e:
                    warnings.warn(f"Failed to read from {path}: {e}")
                    continue
        
        raise ValueError(f"Could not find spot data for {symbol} in any expected path")
    
    def read_futures_series(self, symbol: str = "NIFTY", expiry: Optional[str] = None) -> pd.DataFrame:
        """
        Read futures price series from H5 file
        
        Args:
            symbol: Symbol to read (default: NIFTY)
            expiry: Specific expiry to read (optional)
            
        Returns:
            DataFrame with timestamp index and futures data
        """
        if self._file is None:
            raise RuntimeError("File not opened. Use context manager or call open_file()")
        
        # Common paths for futures data
        possible_paths = [
            f'/futures/{symbol}',
            f'/futures/{symbol.lower()}',
            f'/futures_data/{symbol}',
            f'/{symbol}/futures'
        ]
        
        if expiry:
            possible_paths.extend([
                f'/futures/{symbol}/{expiry}',
                f'/futures_data/{symbol}/{expiry}',
                f'/{symbol}/futures/{expiry}'
            ])
        
        for path in possible_paths:
            if path in self._file:
                try:
                    data = self._file[path][:]
                    if len(data.shape) == 1:
                        df = pd.DataFrame({'price': data})
                        df.index = pd.date_range(start='2024-01-01', periods=len(data), freq='1min')
                    else:
                        df = pd.DataFrame(data)
                        if 'timestamp' in df.columns:
                            df['timestamp'] = pd.to_datetime(df['timestamp'])
                            df.set_index('timestamp', inplace=True)
                    return df
                except Exception as e:
                    warnings.warn(f"Failed to read from {path}: {e}")
                    continue
        
        raise ValueError(f"Could not find futures data for {symbol} in any expected path")
    
    def read_options_table(self, symbol: str = "NIFTY", date_filter: Optional[date] = None) -> pd.DataFrame:
        """
        Read options chain data from H5 file
        
        Args:
            symbol: Symbol to read (default: NIFTY)
            date_filter: Filter by specific date (optional)
            
        Returns:
            DataFrame with options chain data
        """
        if self._file is None:
            raise RuntimeError("File not opened. Use context manager or call open_file()")
        
        # Common paths for options data
        possible_paths = [
            f'/options/{symbol}',
            f'/options/{symbol.lower()}',
            f'/options_data/{symbol}',
            f'/options_chain/{symbol}',
            f'/{symbol}/options'
        ]
        
        for path in possible_paths:
            if path in self._file:
                try:
                    data = self._file[path][:]
                    df = pd.DataFrame(data)
                    
                    # Convert timestamp if present
                    if 'timestamp' in df.columns:
                        df['timestamp'] = pd.to_datetime(df['timestamp'])
                        df.set_index('timestamp', inplace=True)
                    
                    # Filter by date if specified
                    if date_filter and 'timestamp' in df.columns:
                        df = df[df.index.date == date_filter]
                    
                    return df
                except Exception as e:
                    warnings.warn(f"Failed to read from {path}: {e}")
                    continue
        
        raise ValueError(f"Could not find options data for {symbol} in any expected path")
    
    def read_ohlcv_data(self, symbol: str, timeframe: str = "1min") -> pd.DataFrame:
        """
        Read OHLCV data from H5 file
        
        Args:
            symbol: Symbol to read
            timeframe: Timeframe (1min, 5min, 1hour, 1day)
            
        Returns:
            DataFrame with OHLCV data
        """
        if self._file is None:
            raise RuntimeError("File not opened. Use context manager or call open_file()")
        
        # Common paths for OHLCV data
        possible_paths = [
            f'/ohlcv/{symbol}/{timeframe}',
            f'/ohlcv/{symbol.lower()}/{timeframe}',
            f'/bars/{symbol}/{timeframe}',
            f'/{symbol}/ohlcv/{timeframe}',
            f'/{symbol}/bars/{timeframe}'
        ]
        
        for path in possible_paths:
            if path in self._file:
                try:
                    data = self._file[path][:]
                    df = pd.DataFrame(data)
                    
                    # Ensure required columns exist
                    required_cols = ['open', 'high', 'low', 'close', 'volume']
                    if all(col in df.columns for col in required_cols):
                        if 'timestamp' in df.columns:
                            df['timestamp'] = pd.to_datetime(df['timestamp'])
                            df.set_index('timestamp', inplace=True)
                        return df
                except Exception as e:
                    warnings.warn(f"Failed to read from {path}: {e}")
                    continue
        
        raise ValueError(f"Could not find OHLCV data for {symbol} with timeframe {timeframe}")
    
    def get_file_info(self) -> Dict[str, Any]:
        """
        Get information about the H5 file structure
        
        Returns:
            Dictionary with file information
        """
        if self._file is None:
            raise RuntimeError("File not opened. Use context manager or call open_file()")
        
        info = {
            'file_path': str(self.h5_file_path),
            'file_size': self.h5_file_path.stat().st_size,
            'groups': self.get_groups(),
            'datasets': self.get_datasets(),
            'attributes': dict(self._file.attrs)
        }
        
        return info
    
    def list_all_data(self) -> Dict[str, List[str]]:
        """
        List all available data in the H5 file
        
        Returns:
            Dictionary mapping group names to their datasets
        """
        if self._file is None:
            raise RuntimeError("File not opened. Use context manager or call open_file()")
        
        data_map = {}
        groups = self.get_groups()
        
        for group in groups:
            datasets = self.get_datasets(group)
            data_map[group] = datasets
        
        return data_map

def read_h5_to_dataframe(h5_file_path: Union[str, Path], 
                        dataset_path: str,
                        index_col: Optional[str] = None,
                        parse_dates: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Simple function to read H5 file and convert to DataFrame
    
    Args:
        h5_file_path: Path to H5 file
        dataset_path: Path to dataset within H5 file
        index_col: Column to use as index
        parse_dates: Columns to parse as dates
        
    Returns:
        DataFrame
    """
    with H5DataReader(h5_file_path) as reader:
        df = reader.read_dataset(dataset_path, as_dataframe=True)
        
        if index_col and index_col in df.columns:
            df.set_index(index_col, inplace=True)
        
        if parse_dates:
            for col in parse_dates:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col])
        
        return df

def create_h5_from_dataframes(dataframes: Dict[str, pd.DataFrame], 
                             output_path: Union[str, Path],
                             compression: str = 'gzip') -> None:
    """
    Create H5 file from multiple DataFrames
    
    Args:
        dataframes: Dictionary mapping names to DataFrames
        output_path: Output H5 file path
        compression: Compression algorithm to use
    """
    output_path = Path(output_path)
    
    with h5py.File(output_path, 'w') as f:
        for name, df in dataframes.items():
            # Convert DataFrame to structured array
            data = df.to_records(index=True)
            f.create_dataset(name, data=data, compression=compression)
            
            # Store column names as attributes
            f[name].attrs['columns'] = list(df.columns)
            f[name].attrs['index_name'] = df.index.name

def convert_h5_to_csv(h5_file_path: Union[str, Path], 
                      dataset_path: str,
                      output_csv_path: Union[str, Path]) -> None:
    """
    Convert H5 dataset to CSV file
    
    Args:
        h5_file_path: Path to H5 file
        dataset_path: Path to dataset within H5 file
        output_csv_path: Output CSV file path
    """
    df = read_h5_to_dataframe(h5_file_path, dataset_path)
    df.to_csv(output_csv_path)

# Example usage and testing functions
def example_usage():
    """Example usage of H5 utilities"""
    
    # Example 1: Reading spot series
    try:
        with H5DataReader("data/nifty_data.h5") as reader:
            spot_df = reader.read_spot_series("NIFTY")
            print("Spot series shape:", spot_df.shape)
            print("Spot series head:")
            print(spot_df.head())
    except Exception as e:
        print(f"Error reading spot series: {e}")
    
    # Example 2: Reading options table
    try:
        with H5DataReader("data/nifty_data.h5") as reader:
            options_df = reader.read_options_table("NIFTY")
            print("Options table shape:", options_df.shape)
            print("Options table columns:", options_df.columns.tolist())
    except Exception as e:
        print(f"Error reading options table: {e}")
    
    # Example 3: Reading OHLCV data
    try:
        with H5DataReader("data/nifty_data.h5") as reader:
            ohlcv_df = reader.read_ohlcv_data("NIFTY", "1min")
            print("OHLCV data shape:", ohlcv_df.shape)
            print("OHLCV data head:")
            print(ohlcv_df.head())
    except Exception as e:
        print(f"Error reading OHLCV data: {e}")
    
    # Example 4: Getting file information
    try:
        with H5DataReader("data/nifty_data.h5") as reader:
            info = reader.get_file_info()
            print("File info:")
            print(f"  Groups: {info['groups']}")
            print(f"  Datasets: {info['datasets']}")
    except Exception as e:
        print(f"Error getting file info: {e}")

if __name__ == "__main__":
    example_usage()


