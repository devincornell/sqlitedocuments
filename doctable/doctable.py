import sqlite3
import pickle
import pandas as pd
from collections.abc import Iterable

##### DOCUMENT INTERFACE FOR WORKING WITH TEXT DATA #####

class DocTable:
    '''
        This is a base class for working with text documents. 
        It is to be inhereted by a class actually defining the table schema for documents.
    '''
    
    def __init__(self,
                 colschema,
                 fname=':memory:', 
                 tabname='_documents_', 
                 constraints=tuple(),
                 verbose=False,
                 persistent_conn=True,
                ):
        
        self.fname = fname
        self.tabname = tabname
        self.colschema = colschema
        self.constraints = constraints
        self.verbose = verbose
        
        if fname == ':memory:' and not persistent_conn:
            raise ValueError('Must use persistent_conn=True for in-memory databases.')
        
        if persistent_conn:
            self.conn = sqlite3.connect(fname)
        else:
            self.conn = None
        
        self._try_create_table()
        
        self.schema = self._get_schema()
        self.columns = list(self.schema['name'])
        
        self._check_schema()
        
        # keep track of cols with custom data types
        self.types = self.schema['type'].map(lambda t: t.split()[0].lower())

            
    def _try_create_table(self,):
        
        args = (self.tabname, ', '.join(self.colschema + self.constraints))
        return self.query('CREATE TABLE IF NOT EXISTS {} ({})'.format(*args))
        
    def _check_schema(self,):
        '''
            Compares actual table schema to user-provided schema.
        '''
        for colinfo in self.colschema:
            colinfo = colinfo.split()
            cname, ctype = colinfo[0], colinfo[1]
            
            if cname not in self.columns:
                estr = ('Column schema entry "{}" is not found in '
                        'existing table col list: {}')
                raise Exception(estr.format(cname, self.columns))
            
            elif ctype != self.schema.loc[cname,'type']:
                exist_type = self.schema.loc[cname,'type']
                estr = ('Provided column "{}" of type "{}" does not match '
                        'existing data schema type "{}".')
                raise Exception(estr.format(cname, ctype, exist_type))
            else:
                pass
    
    def _get_schema(self):
        '''
            Sets schema from table, parsing out variable names and types.
        '''
        qstr = 'PRAGMA table_Info("{}")'.format(self.tabname,)
        result = tuple(self.query(qstr))
        
        cols = ['cid', 'name', 'type', 'notnull', 'dflt_value','pk']
        schema_df = pd.DataFrame(index=range(len(result)), columns=cols)
        
        for i,row in enumerate(result):
            schema_df.iloc[i] = row
            
        schema_df = schema_df.set_index('name',drop=False)
        
        return schema_df

    
    def _get_existing_tables(self):
        '''
            Gets list of existing tables in the db.
        '''
        res = self.query("SELECT name FROM sqlite_master WHERE type='table'")
        existcols = [col[0] for col in res]
        return existcols
    
    
    def __del__(self):
        '''
            Closes connection upon deletion.
        '''
        if self.conn is not None:
            self.conn.commit()
        
    def __str__(self):
        '''
            Outputs string specifying number of documents in the table.
            
            Output: string of doc info
        '''
        info = ''
        
        ct = self.query('SELECT Count(*) FROM '+self.tabname).__next__()[0]
        info += '<Documents ct: ' + str(ct) + '>'
        
        return info
    
    def commit(self):
        '''
            Commits database changes to file.
        '''
        if self.conn is not None:
            return self.conn.commit()
        # do nothing otherwise; change to exception later?
    
    
    def query(self, qstr, payload=None, many=False, verbose=False, lastrowid=False):
        '''
            Executes raw query using database connection.
            
            Output: sqlite query conn.execute() output.
        '''
        if self.verbose or verbose: print(qstr)
        
        # make a new connection and cursor
        if self.conn is None:
            with sqlite3.connect(self.fname) as conn:
                cursor = conn.cursor()
                e = self._query_exec(cursor, qstr, payload, many)
                if lastrowid:
                    return e, cursor.lastrowid
                else:
                    return e
        
        # use instance connection and make new cursor
        else:
            cursor = self.conn.cursor()
            e = self._query_exec(cursor, qstr, payload, many)
            if lastrowid:
                return e, cursor.lastrowid
            else:
                return e
        
    @staticmethod
    def _query_exec(cursor, qstr, payload, many):
        if payload is None:
            return cursor.execute(qstr)
        else:
            if not many:
                return cursor.execute(qstr,payload)
            else:
                return cursor.executemany(qstr,payload)
    
                
    def add(self, rowdat, ifnotunique=None, lastrowid=False, table=None, **queryargs):
        '''
            Adds a single entry where each column is identified by a key-value pair. 
                Will automatically convert python types to sqlite storage blobs using pickle.
            
            Inputs:
                datadict: dictionary of column name -> value mappings
                ifnotunique: choose what happens when an existing entry matches
                    any UNIQUE criteria specified in the schema.
                    Choose from ('REPLACE', 'IGNORE').
            Output:
                query response
        '''
        if table is None:
            table = self.tabname
        
        rowdat = self._pack(rowdat)
        cols = list(rowdat.keys())
        value_iter = list(rowdat[c] for c in cols)
        n = len(cols)
        
        if ifnotunique is not None:
            replacecode = ' OR {}'.format(ifnotunique.upper())
        else:
            replacecode = ''
        
        args = (replacecode, table, ','.join(cols), ','.join(['?']*n))
        qstr = 'INSERT {} INTO {} ({}) VALUES ({})'.format(*args)
        #qstr = 'INSERT'+replacecode+' INTO ' + self.tabname + '('+','.join(cols)+') VALUES ('+','.join(['?']*n)+')'
        return self.query(qstr, value_iter, **queryargs)
        
    def addmany(self, rowdats, ifnotunique=None, **queryargs):
        '''
            Adds multiple entries to the database, where column names are specified by "keys".
                If "keys" is not specified, will use all columns (including autoincrement columns).
                Will automatically convert python types to sqlite storage blobs using pickle.
                
            Inputs:
                data: lists of tuples representing data for each row
                keys: column names corresponding to each tuple entry
                ifnotunique: choose what happens when an existing entry matches
                    any UNIQUE criteria specified in the schema.
                    Choose from ('REPLACE', 'IGNORE').
            Output:
                sqlite executemany query response
        '''
        # use all columns if keys is not specified
        cols = list(keys) if keys is not None else self.columns
        n = len(cols)
        
        
        if len(self.blob_cols) + len(self.sent_cols) + len(self.token_cols) > 0:
            # need to convert some python objects to blobs for storage
            #payload = ([d[i] if not self.isblob[c] else pickle.dumps(d[i]) for i,c in enumerate(cols)] for d in data)
            payload = [self._pickle_values(cols, values, serialize=True) for values in data]
        else:
            payload = data
        
        replacecode = ' OR ' + ifnotunique if ifnotunique is not None else ''
        qstr = 'INSERT'+replacecode+' INTO ' + self.tabname + '('+','.join(cols)+') VALUES ('+','.join(['?']*n)+')'
        
        return self.query(qstr, payload, many=True, **queryargs)
    
    def delete(self, where, **queryargs):
        '''
            Deletes all rows matching the where criteria.
                
            Inputs:
                where: if "*" is specified, will drop all rows. Otherwise
                    is fed directly into the query statement.
            
            Output:
                query response
        '''
        qstr = 'DELETE FROM {}'.format(self.tabname)
        if where == '*':
            qstr += ' WHERE ' + where
            
        return self.query(qstr, **queryargs)
    
    def delete_all(self, **queryargs):
        qstr = 'DELETE FROM {} *'.format(self.tabname)
        return self.query(qstr, **queryargs)
    
    def update(self, values, where, **queryargs):
        '''
            Updates rows matching the "where" string with specified values.
                
            Inputs:
                values: dictionary of field->values. all rows which meet the where criteria 
                    will have these values assigned
                where: literal SQLite "where" string corresponding to column criteria for 
                    value replacement.
                    The value "*" will match all rows by omitting WHERE statement.
            Output:
                query response
        '''
        dat = self._pack(values)
        cols = list(dat.keys())
        dat_iter = (v for k,v in dat.items())
        
        # UPDATE tasks SET priority = ?, begin_date = ?, end_date = ? WHERE id = ?
        
        colstr = ', '.join(['{} = ?'.format(c) for c in cols])
        qstr = 'UPDATE {} SET {} {}'.format(colstr, self._parse_where(where))
        return self.query(qstr, dat_iter, **queryargs)
    
    
    def getdf(self, *args, **kwargs):
        '''
            Query rows from database, return as Pandas DataFrame.
                
            Inputs:
                See inputs for self.get().
        '''
        results = list(self.get(*args, **kwargs))
        if len(results) > 0:
            sel = list(results[0].keys())
        else:
            try:
                sel
            except NameError:
                sel = list()
        return pd.DataFrame(results, columns=sel)
    
            
    def get(self, sel=None, where=None, orderby=None, groupby=None, limit=None, table=None, verbose=False, asdict=True, **queryargs):
        '''
            Query rows from database as generator.
                
            Inputs:
                sel: list of fields to retrieve with the query
                where: literal SQLite "where" string corresponding to criteria for 
                    value replacement.
                orderby: literal sqlite order by command value. Can be "column_1 ASC",
                    or order by multiple columns using, for instance, "column_1 ASC, column_2 DESC"
                limit: number of rows to retrieve before stopping query. Can be used for quick testing.
                table: table name to retrieve for. Default is object table name, but can query from 
                    others here.
                verbose: True/False flag indicating whether or not output should appear.
                asdict: True/False flag indicating whether rows should be returned as 
                    lists (False) or as dicts with field names (True & default).
                kwargs: to be sent to self.query().
        '''
        
        # use default table if not provided
        tabname = table if table is not None else self.tabname
        
        # choose columns to retrieve
        is_single_col = False
        if sel is None:
            cols = self.columns
        elif isinstance(sel,str):
            cols = [sel,]
            self._check_cols(cols)
            is_single_col = True
        elif isinstance(val, Iterable):
            cols = sel
            self._check_cols(cols)
        else:
            raise ValueError('Column selection must be string '
                'for single column or list/tuple of multiple columns.')
        
        # prepare clauses
        clause_list = (
            self._parse_where(where),
            'ORDER BY '+orderby if orderby is not None else '',
            'LIMIT ' + str(limit) if limit is not None else '',
            'GROUP BY ' + str(groupby) if groupby is not None else '',
        )

        clauses = ' '.join(clause_list)
        qstr = 'SELECT {} FROM {} {}'.format(','.join(cols),tabname,clauses)
        if verbose: print(qstr)
        
        if asdict:
            for dat in self.query(qstr, **queryargs):
                yield {
                    col:val for col,val in zip(cols,self._unpack(cols,dat))
                }
        else:
            for result in self.query(qstr, **queryargs):
                yield self._pack(cols,result)
        
    def _pack(self, rowdict):
        '''
            Converts user-supplied data to compacted data to be stored
                in the database. Edits rowdict in-place, returning reference.
        '''
        cols = tuple(rowdict.keys())
        for col in cols:
            if self.types[col] == 'blob':
                rowdict[col]  = pickle.dumps(rowdict[col])
            elif self.types[col] == 'sentences':
                rowdict[col] = '\n'.join([s.join('\t') for s in rowdict[col]])
            elif self.types[col] == 'tokens':
                rowdict[col] = '\n'.join(rowdict[col])
        
        return rowdict
    
    def _unpack(self, colnames, rowdat):
        '''
            Converts database format data to the user-desired format for custom
                data types.
        '''
        for col,dat in zip(colnames, rowdat):
            if self.types[col] == 'blob':
                yield pickle.loads(dat)
            elif self.types[col] == 'sentences':
                yield [d.split('\t') for d in dat.split('\n')]
            elif self.types[col] == 'tokens':
                dat.split('\n')
            else:
                yield dat
    
    def _parse_where(self, where):
        
        if where is None or \
            (isinstance(where, str) and where is '') or \
            (isinstance(where, dict) and len(where) > 0):
            whereclause = ''
        
        elif isinstance(where, str):
            whereclause = ' WHERE {}'.format(where)
        
        elif isinstance(where, dict):
            conditions = list()
            for col, val in where_dict.items():
                if is_iter(val):
                    itstr = '", "'.join(map(str,val))
                    conditions.append('({} IN ("{}"))'.format(col,itstr))

                elif isinstance(val, dict):
                    conditions.append(self._parse_where_operator(col, val))

                else:
                    conditions.append('({} == "{}")'.format(col, str(val)))

            ' AND '.join(conditions)
            
            whereclause = ' WHERE {}'
    
        return whereclause
            

    @classmethod
    def _parse_where_operator(cls, col, conditions):

        cond_list = list()
        for condition,val in conditions.items():
            cond = condition.lower()

            if cond == 'or':
                cond_list.append('(' + ' OR '.join([cls._parse_operator(col,v) for v in val]) + ')')

            elif cond == 'between':
                if not is_iter(val) or len(val[between_val_key]) is not 2:
                    raise ValueError('The "between" condition of a structured '
                        'query should include value range as a 2-tuple.')
                cond_list.append('{} BETWEEN "{}" AND "{}"'.format(col, *values))

            elif cond in ('in','not in'):
                itstr = '", "'.join(map(str,val))
                cond_list.append('{} {} ("{}")'.format(col,cond.upper(),itstr))

            else:
                cond_list.append('{} {} "{}"'.format(col, cond.upper(), val))
            
        return '(' + ' AND '.join(cond_list) + ')'
        
        
    def _check_cols(self,testcols):
        '''
            Make sure all provided testcols are in the columns.
        '''
        for cn in testcols:
            if cn not in self.columns:
                print(self.colschema)
                raise ValueError('Provided column "{}" '
                    'is not in the database table.'.format(cn))
        
        
def is_iter(val):
    return isinstance(val, list) or isinstance(val, tuple)