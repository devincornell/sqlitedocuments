from __future__ import annotations

import dataclasses
import typing
import sqlalchemy
import sqlalchemy.exc
import pandas as pd

from .statementbuilder import StatementBuilder

if typing.TYPE_CHECKING:
    from ..dbtable import DBTable

@dataclasses.dataclass
class ConnectQuery:
    '''Query interface that is not associated with a particular db table.'''
    conn: sqlalchemy.engine.Connection

    #################### Context Manager ####################
    def __enter__(self) -> ConnectQuery:
        return self
    
    def __exit__(self, exc_type, exc_value, exc_tb) -> None:
        '''Create all tables that exist in metadata.'''
        self.commit()

    def commit(self) -> None:
        return self.conn.commit()

    #################### Select Queries ####################
    def select_chunks(self, 
        cols: typing.List[sqlalchemy.Column],
        chunksize: int = 100, 
        limit: int = None, 
        **kwargs,
    ) -> typing.Generator[typing.List[sqlalchemy.engine.result.Row]]:
        ''' Performs select while querying only a subset of the results at a time. 
            Use when results set will take too much memory.
        '''
        
        offset = 0
        while True:
            
            rows = self.select(cols, offset=offset, limit=chunksize, **kwargs).all()
            chunk = rows[:limit-offset] if limit is not None else rows
            if len(chunk) == 0:
                break
            yield chunk
            
            offset += len(rows)
            
            if len(rows) < chunksize or (limit is not None and offset >= limit):
                break
    
    def select(self, 
        cols: typing.List[sqlalchemy.Column],
        where: typing.Optional[sqlalchemy.sql.expression.BinaryExpression] = None,
        order_by: typing.Optional[typing.List[sqlalchemy.Column]] = None,
        group_by: typing.Optional[typing.List[sqlalchemy.Column]] = None,
        limit: typing.Optional[int] = None,
        wherestr: typing.Optional[str] = None,
        offset: typing.Optional[int] = None,
        **kwargs
    ) -> sqlalchemy.CursorResult:
        '''Most general select method - returns raw sqlalchemy result.
            https://docs.sqlalchemy.org/en/20/core/connections.html#sqlalchemy.engine.CursorResult
            select multiple: result.all()
            select multiple as dataframe: result.df()
            select first row: result.first() use limit=1 NOTE: returns None if no results
            select single row: result.one() NOTE: raises exception if not exactly one result
            select single column: result.scalars().all()
            select single value: result.scalar_one() NOTE: raises exception if not exactly one result
        Args:
            cols: list of sqlalchemy column types created from calling .cols() or other methods.
            where (sqlachemy BinaryExpression): sqlalchemy "where" expression to parse
            order_by: sqlalchemy order_by directive
            group_by: sqlalchemy group_by directive
            limit (int): number of entries to return before stopping
            wherestr (str): raw sql "where" conditionals to add to where input
            **kwargs: passed to self.execute()
        '''
        q = StatementBuilder.select_query(
            cols = cols,
            where = where,
            order_by = order_by,
            group_by = group_by,
            limit = limit,
            wherestr = wherestr,
            offset = offset,
        )
        
        result = self.execute_statement(q, **kwargs)
        result = self.bind_as_dataframe(result)
        return result
    
    @staticmethod
    def bind_as_dataframe(result: sqlalchemy.CursorResult) -> sqlalchemy.CursorResult:
        '''Bind a new method to the result that converts it to a dataframe.'''
        def as_dataframe() -> pd.DataFrame:
            return pd.DataFrame(result.all())
        result.df = as_dataframe
        return result
        

    #################### Insert Queries ####################
    def insert_multi(self, 
        dtable: DBTable,
        data: typing.List[typing.Dict[str, typing.Any]], 
        ifnotunique: typing.Literal['FAIL', 'IGNORE', 'REPLACE'] = 'fail',
        **kwargs
    ) -> sqlalchemy.engine.CursorResult:
        '''Insert multiple rows into the database using executemany-style 
            parameter binding.
        '''
        if not self.is_sequence(data):
            raise TypeError('insert_multi accepts a sequence of rows to insert.')
        q = StatementBuilder.insert_query(dtable.table, ifnotunique=ifnotunique)
        return self.execute_statement(q, data, **kwargs)

    def insert_single(self, 
        dtable: DBTable,
        data: typing.Dict[str, typing.Any], 
        ifnotunique: typing.Literal['FAIL', 'IGNORE', 'REPLACE'] = 'fail',
        **kwargs
    ) -> sqlalchemy.engine.CursorResult:
        ''' Insert a single element into the database using the .values() clause.
            Note: there is a performance cost to this because I enforce 
            the single using .values instead of binding the data. To avoid 
            this cost, past a single-element list to insert_multi instead.
        '''
        q = StatementBuilder.insert_query(
            dtable.table, 
            ifnotunique=ifnotunique
        ).values(**data)
        return self.execute_statement(q, **kwargs)

    #################### Insert Queries ####################
    def update_single(self, 
        dtable: DBTable,
        values: typing.Dict[typing.Union[str,sqlalchemy.Column], typing.Any], 
        where: typing.Optional[sqlalchemy.sql.expression.BinaryExpression] = None, 
        wherestr: typing.Optional[str] = None,
        **kwargs
    ) -> sqlalchemy.engine.CursorResult:
        '''Update row(s) using the .values() clause.'''
        q = StatementBuilder.update_query(
            table = dtable.table,
            where = where,
            wherestr = wherestr,
        ).values(values)         
        return self.execute_statement(q, **kwargs)

    def update_many(self, 
        dtable: DBTable,
        values: typing.List[typing.Dict[typing.Union[str,sqlalchemy.Column], typing.Any]], 
        where: typing.Optional[sqlalchemy.sql.expression.BinaryExpression] = None, 
        wherestr: typing.Optional[str] = None,
        **kwargs
    ) -> sqlalchemy.engine.CursorResult:
        '''Update multiple rows in executemany parameter binding with bindparam().
            https://docs.sqlalchemy.org/en/20/tutorial/data_update.html
            
            NOTE: you MUST use bindparam for this to work. See sqlalchemy example below.
            >>> from sqlalchemy import bindparam
            >>> stmt = (
            ...     update(user_table)
            ...     .where(user_table.c.name == bindparam("oldname"))
            ...     .values(name=bindparam("newname"))
            ... )
            >>> with engine.begin() as conn:
            ...     conn.execute(
            ...         stmt,
            ...         [
            ...             {"oldname": "jack", "newname": "ed"},
            ...             {"oldname": "wendy", "newname": "mary"},
            ...             {"oldname": "jim", "newname": "jake"},
            ...         ],
            ...     )
        '''
        q = StatementBuilder.update_query(
            table = dtable.table,
            where = where,
            wherestr = wherestr,
            #preserve_parameter_order = self.is_sequence(values),
        )
        return self.execute_statement(q, values, **kwargs)

    #################### Delete Queries ####################
    def delete(self, 
        dtable: DBTable,
        where: typing.Optional[sqlalchemy.sql.expression.BinaryExpression] = None, 
        wherestr: typing.Optional[str] = None,
        all: bool = False,
        **kwargs
    ) -> sqlalchemy.engine.CursorResult:
        '''Update row(s) assigning the provided values.'''
        if where is None and wherestr is None and not all:
            raise ValueError('Must provide where or wherestr or set all=True.')

        q = StatementBuilder.delete_query(
            table = dtable.table,
            where = where,
            wherestr = wherestr,
        )
        return self.execute_statement(q, **kwargs)


    #################### Query Execution ####################
    def execute_statement(self, 
        query: typing.Union[sqlalchemy.sql.Insert, sqlalchemy.sql.Select, sqlalchemy.sql.Update, sqlalchemy.sql.Delete], 
        *args, 
        **kwargs
    ) -> sqlalchemy.engine.CursorResult:
        '''Execute a query using a query builder object.'''
        return self.conn.execute(query, *args, **kwargs)
    
    def execute_sql(self, query_str: str, *args, **kwargs) -> sqlalchemy.engine.CursorResult:
        '''Execute raw sql query.'''
        query_str = ' '.join(query_str.split('\n'))
        result = self.conn.execute(sqlalchemy.text(query_str), *args, **kwargs)
        self.bind_as_dataframe(result)
        return result

    @staticmethod
    def is_sequence(obj: typing.Any) -> bool:
        return isinstance(obj, list) or isinstance(obj,tuple)
