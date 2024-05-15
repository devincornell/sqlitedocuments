
import typing
import dataclasses
from typing import Any

#if typing.TYPE_CHECKING:
import sqlalchemy


if typing.TYPE_CHECKING:
    from ..connectcore import ConnectCore

@dataclasses.dataclass
class DBTableBase:
    '''Contains interface for working with table wrappers.'''
    table: sqlalchemy.Table
    core: 'ConnectCore' # make as string? yes, apparently that was the solution

    @property
    def table_name(self) -> str:
        return self.table.name

    def __getitem__(self, key: typing.Union[slice, str, tuple, list]) -> sqlalchemy.Column:
        '''Get a column by name.'''
        if isinstance(key, str):
            # handles table['col1']
            return self.table.c[key]
        elif isinstance(key, (tuple,list)):
            # handles table['col1',], table['col1','col2'], table[('col1','col2')], and table[['col1','col2']]
            return [self.table.c[k] for k in key]
        elif isinstance(key, slice):
            # handles table['col1':'col2']
            all_colnames = [c.name for c in self.table.columns]
            
            # handles table[:]
            if key == slice(None):
                return [self.table.c[k] for k in all_colnames]
            
            try:
                start = all_colnames.index(key.start)
                end = all_colnames.index(key.stop)
            except ValueError as e:
                raise KeyError(f'Column slice is not valid. Choose from these columns: {all_colnames}') from e
            if end < start:
                raise KeyError(f'Start column appears after end column. Reverse start/end of slice to fix.')
            
            return [self.table.c[k] for k in all_colnames[start:end+1]]
        else:
            raise TypeError(f'Invalid key type {type(key)}.')
    
    def __call__(self, *columns) -> typing.List[sqlalchemy.Column]:
        return self.cols(*columns)
    
    def __enter__(self) -> typing.Self:
        return self
    
    def __exit__(self, type, value, traceback):
        pass

    def cols(self, *columns) -> typing.List[sqlalchemy.Column]:
        '''Return a query with only the specified columns.'''
        return [self.table.c[col] if isinstance(col, str) else col for col in columns]
    
    def all_cols(self) -> typing.List[sqlalchemy.Column]:
        return [c for c in self.table.columns]
        
    def inspect_columns(self) -> sqlalchemy.engine.Inspector:
        '''Get engine for this inspector.
        '''
        return self.core.inspect_columns(self.name)

    def inspect_indices(self) -> typing.List[typing.Dict[str, typing.Any]]:
        '''Wraps Inspector.get_indexes(tabname).'''
        return self.core.inspect_indices(self.name)
    
    @property
    def name(self) -> str:
        return self.table.name


