from __future__ import annotations
import typing

if typing.TYPE_CHECKING:
    from ..doctable import DocTable


import sqlalchemy
import dataclasses
import typing
import pandas as pd



from ..schemas import DocTableSchema
from ..util import is_sequence

from .selectqueryargs import SelectQueryArgs
from .errors import *


SingleColumn = typing.Union[str, sqlalchemy.Column]
ColumnList = typing.List[SingleColumn]

typing.Literal['FAIL', 'IGNORE', 'REPLACE']

@dataclasses.dataclass
class Query:
    dtab: DocTable
    
    
    def select_iter(self, cols=None, chunksize=1, limit=None, **kwargs):
        ''' Same as .select except results retrieved from db in chunks.
        Args:
            cols (col name(s) or sqlalchemy object(s)): columns to query
            chunksize (int): size of individual queries to be made. Will
                load this number of rows into memory before yielding.
            limit (int): maximum number of rows to retrieve. Because 
                the limit argument is being used internally to limit data
                to smaller chunks, use this argument instead. Internally,
                this function will load a maximum of limit + chunksize 
                - 1 rows into memory, but yields only limit.
        Yields:
            sqlalchemy result: row data - same as .select() method.
        '''
        for chunk in self.select_chunks(cols=cols, chunksize=chunksize, 
                                                    limit=limit, **kwargs):
            for row in chunk:
                yield row
    
    ######################################## Compound Selects ########################################
    def select_chunks(self, cols: ColumnList = None, chunksize: int = 100, limit: int = None, raw_result: bool = False, **kwargs):
        ''' Performs select while querying only a subset of the results at a time.
        Args:
            cols (col name(s) or sqlalchemy object(s)): columns to query
            chunksize (int): size of individual queries to be made. Will
                load this number of rows into memory before yielding.
            limit (int): maximum number of rows to retrieve. Because 
                the limit argument is being used internally to limit data
                to smaller chunks, use this argument instead. Internally,
                this function will load a maximum of limit + chunksize 
                - 1 rows into memory, but yields only limit.
        Yields:
            result: chunked rows.
        '''
        select_func = self.select_raw if raw_result else self.select
        
        offset = 0
        while True:
            
            rows = select_func(cols, offset=offset, limit=chunksize, **kwargs)
            chunk = rows[:limit-offset] if limit is not None else rows
            
            yield chunk
            
            offset += len(rows)
            
            if (limit is not None and offset >= limit) or len(rows) == 0:
                break

    ######################################## Pandas Select ########################################
    
    def count(self, where: sqlalchemy.sql.expression.BinaryExpression = None, wherestr: str = None, **kwargs) -> int:
        '''Count the number of rows in a table.'''
        cter = sqlalchemy.func.count(self.dtab.columns[0])
        ct = self.select_col(cter, where=where, wherestr=wherestr, limit=1, **kwargs)

        return ct[0]
    
    def select_head(self, n: int = 5, **kwargs) -> pd.DataFrame:
        return self.select_df(limit=n, **kwargs)
        
    def select_series(self,
            col: SingleColumn,
            where: sqlalchemy.sql.expression.BinaryExpression = None,
            orderby: typing.Union[sqlalchemy.Column, typing.List[sqlalchemy.Column]] = None,
            groupby: typing.Union[sqlalchemy.Column, typing.List[sqlalchemy.Column]] = None,
            limit: int = None,
            wherestr: str = None,
            offset: int = None,
            **kwargs
        ) -> pd.Series:
        '''Select returning pandas Series.
        Args:
            col: column to query. Passed directly to .select() 
                method.
            *args: args to regular .select() method.
            **kwargs: args to regular .select() method.
        Returns:
            pandas series: enters rows as values.
        '''
        return pd.Series(self.select_col(
            col = col,
            where = where,
            orderby = orderby,
            groupby = groupby,
            limit = limit,
            wherestr = wherestr,
            offset = offset,
            **kwargs
        ))
        
    def select_df(self, 
            cols: ColumnList = None,
            where: sqlalchemy.sql.expression.BinaryExpression = None,
            orderby: typing.Union[sqlalchemy.Column, typing.List[sqlalchemy.Column]] = None,
            groupby: typing.Union[sqlalchemy.Column, typing.List[sqlalchemy.Column]] = None,
            limit: int = None,
            wherestr: str = None,
            offset: int = None,
            **kwargs
        ) -> pd.DataFrame:
        '''Select returning dataframe.
        Args:
            cols: sequence of columns to query. Must be sequence,
                passed directly to .select() method.
            *args: args to regular .select() method.
            **kwargs: args to regular .select() method.
        Returns:
            pandas dataframe: Each row is a database row,
                and output is not indexed according to primary 
                key or otherwise. Call .set_index('id') on the
                dataframe to envoke this behavior.
        '''
        return pd.DataFrame(self.select_raw(
            cols = self.parse_input_cols(cols),
            where = where,
            orderby = orderby,
            groupby = groupby,
            limit = limit,
            wherestr = wherestr,
            offset = offset,
            **kwargs
        ))
        
    ######################################## Single-column Select ########################################
    
    def select_col(self, 
            col: SingleColumn,
            where: sqlalchemy.sql.expression.BinaryExpression = None,
            orderby: typing.Union[sqlalchemy.Column, typing.List[sqlalchemy.Column]] = None,
            groupby: typing.Union[sqlalchemy.Column, typing.List[sqlalchemy.Column]] = None,
            limit: int = None,
            wherestr: str = None,
            offset: int = None,
            **kwargs
        ) -> typing.List[typing.Any]:
        '''Select values of a single column.'''
        
        rows = self.select_raw(
            cols = self.parse_input_col(col),
            where = where,
            orderby = orderby,
            groupby = groupby,
            limit = limit,
            wherestr = wherestr,
            offset = offset,
            **kwargs
        )
        return [r[0] for r in rows]

    ######################################## Base Selection Funcs ########################################
    def select_scalar(self, 
            col: SingleColumn,
            where: sqlalchemy.sql.expression.BinaryExpression = None,
            orderby: typing.Union[sqlalchemy.Column, typing.List[sqlalchemy.Column]] = None,
            groupby: typing.Union[sqlalchemy.Column, typing.List[sqlalchemy.Column]] = None,
            wherestr: str = None,
            offset: int = None,
            **kwargs
        ) -> typing.List[typing.Any]:
        '''Select values of a single column.'''
        
        row = self.select_first(
            cols = self.parse_input_col(col),
            where = where,
            orderby = orderby,
            groupby = groupby,
            wherestr = wherestr,
            offset = offset,
            raw_result = True,
            **kwargs
        )
        return row[0]


    def select_col(self, 
            col: SingleColumn,
            where: sqlalchemy.sql.expression.BinaryExpression = None,
            orderby: typing.Union[sqlalchemy.Column, typing.List[sqlalchemy.Column]] = None,
            groupby: typing.Union[sqlalchemy.Column, typing.List[sqlalchemy.Column]] = None,
            limit: int = None,
            wherestr: str = None,
            offset: int = None,
            **kwargs
        ) -> typing.List[typing.Any]:
        '''Select values of a single column.'''
        
        rows = self.select_raw(
            cols = self.parse_input_col(col),
            where = where,
            orderby = orderby,
            groupby = groupby,
            limit = limit,
            wherestr = wherestr,
            offset = offset,
            **kwargs
        )
        return [r[0] for r in rows]
    
    
    def select_first(self,
            cols: ColumnList = None,
            where: sqlalchemy.sql.expression.BinaryExpression = None,
            orderby: typing.Union[sqlalchemy.Column, typing.List[sqlalchemy.Column]] = None,
            groupby: typing.Union[sqlalchemy.Column, typing.List[sqlalchemy.Column]] = None,
            wherestr: str = None,
            offset: int = None,
            raw_result: bool = False, 
            **kwargs
        ) -> DocTableSchema:
        
        select_func = self.select if not raw_result else self.select_raw
        results = select_func(
            cols = cols,
            where = where,
            orderby = orderby,
            groupby = groupby,
            limit = 1,
            wherestr = wherestr,
            offset = offset,
            **kwargs
        )
        
        if len(results) == 0:
            raise LookupError('No results were returned. Needed to error '
                'so this result wasn not confused with case where actual '
                'result is None. If not sure about result, use regular '
                '.select() method with limit=1.')

        return results[0]

    def select(self, 
            cols: typing.List[sqlalchemy.Column] = None,
            where: sqlalchemy.sql.expression.BinaryExpression = None,
            orderby: typing.Union[sqlalchemy.Column, typing.List[sqlalchemy.Column]] = None,
            groupby: typing.Union[sqlalchemy.Column, typing.List[sqlalchemy.Column]] = None,
            limit: int = None,
            wherestr: str = None,
            offset: int = None,
            **kwargs
        ) -> typing.List[DocTableSchema]:
        '''
        Select some basic shit.
        Description: Because output must be iterable, returns special column results 
            by performing one query per row. Can be inefficient for many smaller 
            special data information.
        
        Args:
            cols: list of sqlalchemy datatypes created from calling .col() method.
            where (sqlachemy BinaryExpression): sqlalchemy "where" object to parse
            orderby: sqlalchemy orderby directive
            groupby: sqlalchemy gropuby directive
            limit (int): number of entries to return before stopping
            wherestr (str): raw sql "where" conditionals to add to where input
            **kwargs: passed to self.execute()
        Yields:
            sqlalchemy result object: row data

        '''
        results = self.select_raw(
            cols = self.parse_input_cols(cols),
            where = where,
            orderby = orderby,
            groupby = groupby,
            limit = limit,
            wherestr = wherestr,
            offset = offset,
            **kwargs
        )
        return [self.dtab.schema.row_to_object_interface(r) for r in results]

    def select_raw(self, 
            cols: typing.List[sqlalchemy.Column] = None,
            where: sqlalchemy.sql.expression.BinaryExpression = None,
            orderby: typing.Union[sqlalchemy.Column, typing.List[sqlalchemy.Column]] = None,
            groupby: typing.Union[sqlalchemy.Column, typing.List[sqlalchemy.Column]] = None,
            limit: int = None,
            wherestr: str = None,
            offset: int = None,
            **kwargs
        ) -> typing.List[typing.Dict[str, typing.Any]]:
        '''
        Select some basic shit.
        Description: Because output must be iterable, returns special column results 
            by performing one query per row. Can be inefficient for many smaller 
            special data information.
        
        Args:
            cols: list of sqlalchemy datatypes created from calling .col() method.
            where (sqlachemy BinaryExpression): sqlalchemy "where" object to parse
            orderby: sqlalchemy orderby directive
            groupby: sqlalchemy gropuby directive
            limit (int): number of entries to return before stopping
            wherestr (str): raw sql "where" conditionals to add to where input
            **kwargs: passed to self.execute()
        Yields:
            sqlalchemy result object: row data

        '''
        q = SelectQueryArgs(
            cols = self.parse_input_cols(cols),
            where = where,
            orderby = orderby,
            groupby = groupby,
            limit = limit,
            wherestr = wherestr,
            offset = offset,
        ).get_query()
        
        return self.dtab.execute(q, **kwargs).fetchall()
    
    ############################## Parse User Input ##############################
    def parse_input_cols(self, cols: ColumnList) -> typing.List[sqlalchemy.Column]:
        '''Pass variable passed to cols.'''        
        if cols is None:
            cols = list(self.dtab.columns)
        else:
            if not is_sequence(cols):
                raise TypeError('cols argument should be a list of columns.')

            cols = [self.dtab.col(c) if isinstance(c,str) else c for c in cols]
        
        return cols
    
    def parse_input_col(self, col: SingleColumn) -> typing.List[sqlalchemy.Column]:
        if is_sequence(col):
            raise TypeError('col argument should be single column.')
        
        use_col = self.dtab.col(col) if isinstance(col,str) else col
        return [use_col]


    ######################################## High-level inserts that infer type. ########################################

    ######################################## Insert Multiple ########################################
    def insert_multi(self, 
            schema_objs: ColumnList, 
            ifnotunique: typing.Literal['FAIL', 'IGNORE', 'REPLACE'] = 'fail',
            **kwargs
        ) -> sqlalchemy.engine.ResultProxy:
        '''Insert multiple rows as objects into the db.'''
        if not is_sequence(schema_objs):
            raise TypeError('insert_multi and insert_multi_raw accept a list or '
            f'tuple of schema objects to insert.')
        obj_dicts = [self.dtab.schema.object_to_dict_interface(o) for o in schema_objs]
        return self.insert_multi_raw(obj_dicts, ifnotunique=ifnotunique, **kwargs)
        
    def insert_multi_raw(self, 
            datum: typing.List[typing.Dict[str, typing.Any]], 
            ifnotunique: typing.Literal['FAIL', 'IGNORE', 'REPLACE'] = 'fail',
            **kwargs
        ) -> sqlalchemy.engine.ResultProxy:
        '''Insert multiple rows as dictionaries into the db.'''
        if not is_sequence(datum):
            raise TypeError('insert_multi and insert_multi_raw accept a list or '
            f'tuple of schema objects to insert.')
        q = self.insert_query(ifnotunique=ifnotunique)
        return self.dtab.execute(q, datum, **kwargs)

    ######################################## Insert Single ########################################
    def insert_single(self, 
            obj: DocTableSchema, 
            ifnotunique: typing.Literal['FAIL', 'IGNORE', 'REPLACE'] = 'fail', 
            **kwargs
        ) -> sqlalchemy.engine.ResultProxy:
        if is_sequence(obj):
            raise TypeError(f'Provided object must not be a sequence. If you '
                f'intended to insert multiple objects, use .q.insert_multi()')
        obj_dict = self.dtab.schema.object_to_dict_interface(obj)
        return self.insert_single_raw(obj_dict, ifnotunique=ifnotunique, **kwargs)

    def insert_single_raw(self, 
            data: typing.Dict[str, typing.Any], 
            ifnotunique: typing.Literal['FAIL', 'IGNORE', 'REPLACE'] = 'fail',
            **kwargs
        ) -> sqlalchemy.engine.ResultProxy:
        if is_sequence(data):
            raise TypeError('insert_single and insert_single_raw accept a '
            f'single schema object for insertion.')
        q = self.insert_query(ifnotunique=ifnotunique)
        return self.dtab.execute(q, data, **kwargs)

    ######################################## Build Insert Query ########################################
    def insert_query(self, ifnotunique: typing.Literal['FAIL', 'IGNORE', 'REPLACE'] = 'fail') -> sqlalchemy.sql.Insert:
        self._check_readonly('insert')
        q: sqlalchemy.sql.Select = sqlalchemy.sql.insert(self.dtab.table)
        q = q.prefix_with('OR {}'.format(ifnotunique.upper()))
        return q

    ############################## Update Methods ##############################
    def update(self, 
            values: typing.Dict[typing.Union[str,sqlalchemy.Column], typing.Any], 
            where: sqlalchemy.sql.expression.BinaryExpression = None, 
            wherestr: str = None,
            **kwargs
        ) -> sqlalchemy.engine.ResultProxy:
        '''Update row(s) assigning the provided values.
        Args:
            values (dict<colname->value> or list<dict> or list<(col,value)>)): 
                values to populate rows with. If dict, will insert those values
                into all rows that match conditions. If list of dicts, assigns
                expression in value (i.e. id['year']+1) to column. If list of 
                (col,value) 2-tuples, will assign value to col in the order 
                provided. For example given row values x=1 and y=2, the input
                [(x,y+10),(y,20)], new values will be x=12, y=20. If opposite
                order [(y,20),(x,y+10)] is provided new values would be y=20,
                x=30. In cases where list<dict> is provided, this behavior is 
                undefined.
            where (sqlalchemy condition): used to match rows where
                update will be applied.
            wherestr (sql string condition): matches same as where arg.
        Returns:
            SQLAlchemy result proxy object
        '''
        self._check_readonly('update')
        
        q: sqlalchemy.sql.Update = sqlalchemy.sql.update(
            self.dtab.table, 
            preserve_parameter_order = is_sequence(values),
        )
        
        if where is not None:
            q = q.where(where)
        if wherestr is not None:
            q = q.where(sqlalchemy.text(wherestr))
        
        q = q.values(values)
         
        return self.dtab.execute(q, **kwargs)

    ############################## Delete Methods ##############################
    
    def delete(self, 
            where: sqlalchemy.sql.expression.BinaryExpression = None, 
            wherestr: str = None,
            delete_all: bool = False, 
            vacuum: bool = False,
            **kwargs,
        ) -> sqlalchemy.engine.ResultProxy:
        '''Delete rows from the table that meet the where criteria.
        Args:
            where (sqlalchemy condition): criteria for deletion.
            wherestr (sql string): addtnl criteria for deletion.
            vacuum (bool): will execute vacuum sql command to reduce
                storage space needed by SQL table. Use when deleting
                significant ammounts of data.
        Returns:
            SQLAlchemy result proxy object.
        '''
        self._check_readonly('delete')
        
        if where is None and wherestr is None and not delete_all:
            raise ValueError(f'Must set delete_all=True to delete all rows. This is '
                'a safety precaution.')
        
        q: sqlalchemy.sql.Delete = sqlalchemy.sql.delete(self.dtab.table)

        if where is not None:
            q = q.where(where)
        if wherestr is not None:
            q = q.where(sqlalchemy.text(wherestr))
        
        r = self.dtab.execute(q, **kwargs)
        
        if vacuum:
            self.dtab.execute('VACUUM')
        
        # https://kite.com/python/docs/sqlalchemy.engine.ResultProxy
        return r




    ############################## General Purpose ##############################

    def _check_readonly(self, funcname: str) -> None:
        if self.dtab.readonly:
            raise SetToReadOnlyMode(f'Cannot {funcname} when doctable set to readonly.')





