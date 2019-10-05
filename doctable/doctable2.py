import collections
from time import time
import pprint
import random
import pandas as pd
import os.path

# operators like and_, or_, and not_, functions like sum, min, max, etc
import sqlalchemy.sql as op
from sqlalchemy.sql import func
import sqlalchemy as sa

from .coltypes import TokensType

class DocTable2:
    type_map = {
        'biginteger':sa.BigInteger,
        'boolean':sa.Boolean,
        'date':sa.Date,
        'datetime':sa.DateTime,
        'enum':sa.Enum,
        'float':sa.Float,
        'integer':sa.Integer,
        'interval':sa.Interval,
        'largebinary':sa.LargeBinary,
        'numeric':sa.Numeric,
        'pickle':sa.PickleType,
        'smallinteger':sa.SmallInteger,
        'string':sa.String,
        'text':sa.Text,
        'time':sa.Time,
        'unicode':sa.Unicode,
        'unicodetext':sa.UnicodeText,
        'tokens':TokensType, # custom datatype
        'paragraphs':TokensType, # custom datatype
    }
    
    constraint_map = {
        'unique_constraint': sa.UniqueConstraint,
        'check_constraint': sa.CheckConstraint,
        'primarykey_constraint': sa.PrimaryKeyConstraint,
        'index': sa.Index,
    }
    
    def __init__(self, schema=None, tabname='_documents_', fname=':memory:', engine='sqlite', persistent_conn=True, verbose=False, check_schema=True, new_db=True):
        '''Create new database.
        
        '''
        
        # in cases where user did not want to create new db but a db does not 
        # exist
        if fname != ':memory:' and not os.path.exists(fname) and not new_file:
            raise ValueError('new_db is set to true and the database does not '
                             'exist yet.')
        
        # separate tables for custom data types and main table
        self.tabname = tabname
        self.verbose = verbose
        
        self.engine = sa.create_engine('{}:///{}'.format(engine,fname))
        self._schema = schema
            
        # actually create table
        self.metadata = sa.MetaData()
        
        if self._schema is not None:
            columns = self._parse_column_schema(schema)
            self._table = sa.Table(self.tabname, self.metadata, *columns)
            self.metadata.create_all(self.engine)
        else:
            self._table = sa.Table(self.tabname, self.metadata, autoload=True, autoload_with=self.engine)
            
        # connect with database engine
        if persistent_conn:
            self.conn = self.engine.connect()
        else:
            self.conn = None
    
    def __delete__(self):
        if self.conn is not None:
            self.conn.close()
            
    def __str__(self):
        return '<DocTable2::{} ct: {}>'.format(self.tabname, self.num_rows)
        
        
    ################# INITIALIZATION METHODS ##################
    
    def _parse_column_schema(self,schema):
        self.colnames = [c[0] for c in schema]
        columns = list()
        for colinfo in schema:
            if len(colinfo) == 2:
                colname, coltype = colinfo
                colargs, coltypeargs = dict(), dict()
            elif len(colinfo) == 3:
                colname, coltype, colargs = colinfo
                coltypeargs = dict()
            elif len(colinfo) == 4:
                colname, coltype, colargs, coltypeargs = colinfo
            else:
                raise ValueError(coltype_error_str)
            
            if coltype not in self.constraint_map: # if coltype is regular column
                typ = self._get_sqlalchemy_type(coltype)
                col = sa.Column(colname, typ(**coltypeargs), **colargs)
                columns.append(col)

            else: # column is actually a constraint (not regular column)
                if coltype  == 'index':
                    const = self.constraint_map[coltype](colname, *colargs, **coltypeargs)
                elif coltype in ('check_constraint',):
                    # in this case, colname should be a constraint string (i.e. "age > 0")
                    const = self.constraint_map[coltype](colname, **colargs)
                else:
                    if not is_sequence(colname):
                        raise ValueError('First column argument on {} should '
                            'be a sequence of columns.'.format(coltype))
                    const = self.constraint_map[coltype](*colname, **colargs)
                columns.append(const)
        return columns


                
    def _get_sqlalchemy_type(self,typstr):
        '''Maps typstr with an sqlalchemy data type (or doctable custom type).
        '''
        if typstr not in self.type_map:
            raise ValueError('Provided column type must match '
                'one of {}.'.format(self.type_map.keys()))
        else:
            return self.type_map[typstr]
    
    #def _check_schema(self,schema):
    
    
    ################# INSERT METHODS ##################
    
    def insert(self, rowdat, ifnotunique='fail'):
        '''Insert a row.
        Args:
            rowdat (list<dict> or dict): row data to insert.
            ifnotunique: way to handle inserted data if it breaks
                a table constraint. Choose from FAIL, IGNORE, REPLACE.
        Returns:
            sqlalchemy query result object
        '''
        q = sa.sql.insert(self._table, rowdat)
        q = q.prefix_with('OR {}'.format(ifnotunique.upper()))
        r = self.execute(q)
    
    
    ################# SELECT METHODS ##################
    
    def select_first(self, *args, **kwargs):
        '''Perform regular select query returning only the first result.
        '''
        return self.select(*args, limit=1, **kwargs)[0]
    
    def sel_df(self, *args, **kwargs):
        '''Select returning dataframe.'''
        sel = self.select(*args, **kwargs)
        return pd.DataFrame(list(sel))
    
    def sel_series(self, col, *args, **kwargs):
        '''Select returning pandas Series.
        '''
        sel = self.select(col, *args, **kwargs)
        return pd.Series(sel)
    
    def select(self, cols=None, where=None, orderby=None, groupby=None, limit=None):
        '''Perform select query, yield result for each row.
        
        Description: Because output must be iterable, returns special column results 
            by performing one query per row. Can be inefficient for many smaller 
            special data information.
        
        Args:
            cols: list of sqlalchemy datatypes created from calling .col() method.
            where: sqlalchemy where object to parse
            orderby: sqlalchemy orderby directive
            groupby: sqlalchemy gropuby directive
            limit (int): number of entries to return before stopping
        Yields:
            dictionary: row data
        '''
        return_single = False
        if cols is None:
            cols = list(self._table.columns)
        else:
            if not is_sequence(cols):
                return_single = True
                cols = [cols]
                
        # query colunmns in main table
        result = self._exec_select_query(cols,where,orderby,groupby,limit)
        # this is the result object:
        # https://kite.com/python/docs/sqlalchemy.engine.ResultProxy
        
        # NOTE: I USE LIST RETURN BECAUSE UNDERLYING SQL ENGINE
        # WILL LOAD THE DATA INTO MEMORY ANYWAYS. THIS JUST PRESENTS
        # A MORE FLEXIBLE INTERFACE TO THE USER.
        # row is an object that can be accessed by col keyword
        # i.e. row['id'] or num index, i.e. row[0].
        if return_single:
            return [row[0] for row in result]
        else:
            return [row for row in result]
                
    
                
    def _exec_select_query(self, cols, where, orderby, groupby, limit):
        
        q = sa.sql.select(cols)
        
        if where is not None:
            q = q.where(where)
        if orderby is not None:
            q = q.order_by(orderby)
        if groupby is not None:
            q = q.groupby(orderby)
        if limit is not None:
            q = q.limit(limit)
        
        result = self.execute(q)
        
        return result
    


    
    #################### Update Methods ###################
    
    def update(self,values,where=None):
        '''Update row(s) assigning the provided values.
        '''
            
        # update the main column values
        q = sa.sql.update(self._table).values(values)
        if where is not None:
            q = q.where(where)
        r = self.execute(q)
        
        return r
    
    
    #################### Delete Methods ###################
    
    def delete(self,where=None):
        '''Delete rows from the table that meet the where criteria.
        '''
        q = sa.sql.delete(self._table)
        if where is not None:
            q = q.where(where)
        r = self.execute(q)
        return r
    
    ################# CRITICAL SQL METHODS ##################
    
    def execute(self, query):
        '''Execute an sql command. Called by most higher-level functions.
        '''
        if self.verbose: print('DocTable2 Query: {}'
                               ''.format(query))
        
        # try to parse
        result = self._execute(query)
        return result
        
    def _execute(self, query):
        # takes raw query object
        if self.conn is not None:
            r = self.conn.execute(query)
        else:
            with self.engine.connect() as conn:
                r = conn.execute(query)
        return r
    
    
    #################### Accessor Methods ###################
    
    def col(self,name):
        '''Accesses a column object.
        '''
        return self._table.c[name]
    
    def __getitem__(self, colname):
        '''Accesses a column object by calling .col().'''
        return self.col(colname)
        
    @property
    def table(self):
        return self._table
        
    @property
    def num_rows(self):
        return self.select_first(func.count(self._table))
    
    def print_schema(self):
        return pprint.pformat(self._schema)
    
    def count(self,where=None):
        if where is None:
            return self.num_rows
        
        cter = func.count(self._table)
        ct = self.select_first(cter,where=where)
        return ct
    
    def next_id(self, idcol='id'):
        return self.select_first(func.max(self[idcol]))+1
    
    #################### Bootstrapping Methods ###################
    
    
    def select_bootstrap(self, cols=None, nsamp=None, where=None):
        idwaves = self._bs_sampids(nsamp, where=where)
        results = list()
        for idwave in idwaves:
            results += self.select(cols, where=self.fkid_col.in_(idwave))
        return results
    
    
    def select_bootstrap_iter(self, cols=None, nsamp=None, where=None):
        idwaves = self._bs_sampids(nsamp, where=where)
        results = list()
        for idwave in idwaves:
            for row in self.select_iter(cols, where=self.fkid_col.in_(idwave)):
                yield row
                
            
    def _bs_sampids(self,nsamp,**kwargs):
        if nsamp == None:
            nsamp = self.num_rows
        print(kwargs)
        
        ids = self.select(self.fkid_col, **kwargs) # includes WHERE clause args
        cts = collections.Counter(random.choices(ids,k=nsamp))
        
        idwaves = list()
        for i in range(max(cts.values())):
            ids = [idx for idx,ct in cts.items() if ct > i]
            idwaves.append(ids)
        return idwaves
    
    

coltype_error_str = ('Provided column schema must '
                    'be a two-tuple (colname, coltype), three-tuple '
                    '(colname,coltype,{sqlalchemy type data}), or '
                    'four-tuple (colname, coltype, sqlalchemy type data, '
                    '{sqlalchemy column arguments}).')
    

def is_sequence(obj):
    return isinstance(obj, list) or isinstance(obj,set) or isinstance(obj,tuple)


