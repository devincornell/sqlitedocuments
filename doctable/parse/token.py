
import typing
import dataclasses
import collections
import doctable
import pickle

class PropertyNotAvailable(Exception):
    self.message = '{prop} is not available in Token because {parsefeatname} was not enabled while processing with Spacy.'
    def __init__(self, prop, parsefeatname):
        super.__init__(self.message.format(prop, parsefeatname))


@dataclasses.dataclass
class Token:
    i: int
    text: str
    dep: str
    tag: str
    childs: list[Token]
    tree: doctable.ParseTree
    otherdata: dict = {}
    userdata: dict = {}
    parent: Token = None

    def __post_init__(self):
        ''' Create references to parents recursively.
        '''
        # adding references to parent
        for child in self.childs:
            child.parent = self

        # set up for subscripting
        self.chainmap = collections.ChainMap(self.__dict__, 
                            self.otherdata, self.userdata)
    
    ########################## Factory methods ##########################

    #def __init__(self, node, userdata_map=dict(), parent=None, tree=None):

    @classmethod
    def from_spacy(cls, doc: typing.Any, 
                        text_parse_func:typing.Callable=lambda x: x, 
                        userdata_map: dict[str,typing.Callable]=dict(), 
                        tree:doctable.ParseTree=None):
        ''' Return tokens recursively from doc object.
                doc (spacy.Token): token to extract userdata from
                text_parse_func: mapping to store text data
                userdata_map: used to create custom user data
        '''
        newtoken = cls.__class__(
            i = doc.i,
            dep = doc.dep_,
            tag = doc.tag_,
            text = text_parse_func(doc),
            otherdata = {
                'pos': doc.pos_ if doc.doc.is_tagged else None,
                'ent': doc.ent_type_ if doc.doc.is_nered else None,
            }
            userdata = {attr:func(doc) for attr,func in userdata_map.items()}
            
            # references
            parent = parent,
            tree=tree,
            childs = [cls.from_spacy(child, text_parse_func=text_parse_func, 
                        userdata_map=userdata_map, tree=tree) 
                        for child in doc.children],
        )
        return newtoken

    def from_dict(self, tok_data, tree):
        ''' Create new token recursively using a dictionary tree structure.
        '''
        newtoken = self.__class__(
            i = tok_data['i'],
            text = tok_data['text'],
            dep = tok_data['dep'],
            tag = tok_data['tag'],
            otherdata = ndict['otherdata'],
            userdata = ndict['userdata'],
            childs = [self.from_dict(td) for td in ndict['childs']],
        )
        return newtoken

    ########################## Serialization ##########################
    def as_dict(self):
        ''' Convert self to a dict tree - used when storing data.
        '''
        data = dict(
            i=self.i,
            text=self.text,
            tag=self.tag,
            dep=self.dep,
            otherdata=self.otherdata,
            userdata=self.userdata,
            childs=[c.as_dict() for c in self.childs],
        )
        return data
    
    def as_pickle(self):
        ''' Return pickled dictionary data.
        '''
        return pickle.dumps(self.as_dict())
        
    ########################## Built-In Methods ##########################
    def __str__(self):
        return self.text
    
    def __repr__(self):
        return f'{self.__class__.__name__}({self.text})'
    
    def __getitem__(self,ind):
        return self.chainmap[ind]
    
    def __iter__(self):
        return iter(self.childs)

    ########################## Properties ##########################
    @property
    def is_root(self):
        return self.parent is None

    @property
    def pos(self):
        if self.otherdata['pos'] is None:
            raise PropertyNotAvailable('Part-of-speech tag', 'POS-tagging')
        return self.otherdata['pos']

    @property
    def ent(self):
        if self.otherdata['ent'] is None:
            raise PropertyNotAvailable('Entity type', 'NER')
        return self.otherdata['ent']

    @property
    def is_none(self):
        return False

    ########################## Navigation Functions ##########################

    def get_childs(self, dep=None, pos=None, matchfunc=None):
        ''' Get children with the specified relations.
        Args:
            dep (sequence or string): dependency relations to match on.
            pos (sequence or string): pos to match on.
            matchfunc (function or None): additional custom matching function.
        '''
        if isinstance(dep, str):
            dep = set([dep])

        if isinstance(pos, str):
            pos = set([pos])

        childs = list()
        for c in self.childs:
            if (dep is None or c.dep in dep): # nested to make more readable?
                if (pos is None or c.pos in pos):
                    if (matchfunc is None or matchfunc(c)):
                        childs.append(c)
        return childs

    def get_child(self, *args, allow_multiple: bool=False, **kwargs):
        ''' Get first child with the given dependency relation.
        Args:
            *args: passed to get_childs
            allow_multiple: don't allow 
            **kwargs: passed to get_childs
        Raises:
            ValueError when the token has more than one dependency with the 
                given relation.
        '''
        childs = self.get_childs(*args, **kwargs)
        if len(childs) == 1 or (len(childs) and allow_multiple):
            return childs[0]
        elif not len(childs):
            return NoneToken()
        else:
            raise ValueError(f'There is more than one dependency matching {args}, {kwargs}.')
    
    def get_preps(self, as_str=False):
        ''' Gets chained prepositional phrases starting at the current token.
        Returns:
            tuple of prep, pobj.
        '''
        preps = list()
        for prep in self.get_childs({'prep', 'dative'}):
            if as_str:
                pairs = (prep.t, [p.t for p in prep.get_childs('pobj') if not p.is_none])
            else:
                pairs = (prep, [p for p in prep.get_childs('pobj') if not p.is_none])
            preps.append(pairs)
        
        return preps
    
    ########################## Accumulation Functions ##########################
    def bubble_accum(self, func):
        aggregated_list = func(self)
        for child in self.childs:
            aggregated_list += child.bubble_accum(func)
        return aggregated_list
    
    def bubble_reduce(self, func, agg_data):
        agg_data = func(self, agg_data)
        for child in self.childs:
            agg_data = child.bubble_reduce(func, agg_data)
        return agg_data
    

class NoneToken(Token):
    @property
    def is_none(self):
        return True
    def __str__(self):
        return 'NoneToken()'
