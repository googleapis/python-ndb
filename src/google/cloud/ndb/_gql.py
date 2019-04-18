import itertools
import re

from google.cloud.ndb import exceptions
from google.cloud.ndb import query as query_module
from google.cloud.ndb import model
from google.cloud.ndb import _datastore_query


class GQL(object):
    """A GQL parser for NDB queries.

    GQL is a SQL-like language which supports more object-like semantics
    in a language that is familiar to SQL users.

    - reserved words are case insensitive
    - names are case sensitive

    The syntax for SELECT is fairly straightforward:

    SELECT [[DISTINCT] <property> [, <property> ...] | * | __key__ ]
        [FROM <entity>]
        [WHERE <condition> [AND <condition> ...]]
        [ORDER BY <property> [ASC | DESC] [, <property> [ASC | DESC] ...]]
        [LIMIT [<offset>,]<count>]
        [OFFSET <offset>]
        [HINT (ORDER_FIRST | FILTER_FIRST | ANCESTOR_FIRST)]
        [;]
    <condition> := <property> {< | <= | > | >= | = | != | IN} <value>
    <condition> := <property> {< | <= | > | >= | = | != | IN} CAST(<value>)
    <condition> := <property> IN (<value>, ...)
    <condition> := ANCESTOR IS <entity or key>

    The class is implemented using some basic regular expression tokenization
    to pull out reserved tokens and then the recursive descent parser will act
    as a builder for the pre-compiled query. This pre-compiled query is then
    used by google.cloud.ndb.query.gql to build an NDB Query object.
    """

    TOKENIZE_REGEX = re.compile(
        r"""
        (?:'[^'\n\r]*')+|
        <=|>=|!=|=|<|>|
        :\w+|
        ,|
        \*|
        -?\d+(?:\.\d+)?|
        \w+(?:\.\w+)*|
        (?:"[^"\s]+")+|
        \(|\)|
        \S+
        """,
        re.VERBOSE | re.IGNORECASE,
    )

    RESERVED_KEYWORDS = frozenset(
        (
            "SELECT",
            "DISTINCT",
            "FROM",
            "WHERE",
            "IN",
            "IS",
            "AND",
            "OR",
            "NOT",
            "ORDER",
            "BY",
            "ASC",
            "DESC",
            "GROUP",
            "LIMIT",
            "OFFSET",
            "HINT",
            "ORDER_FIRST",
            "FILTER_FIRST",
            "ANCESTOR_FIRST",
        )
    )

    __ANCESTOR = -1

    _kind = None
    _keys_only = False
    __projection = None
    __distinct = False
    __has_ancestor = False
    __offset = -1
    __limit = -1
    __hint = ""

    def __init__(
        self, query_string, _app=None, _auth_domain=None, namespace=None
    ):
        """Parses the input query into the class as a pre-compiled query.

        Args:
            query_string (str): properly formatted GQL query string.
            namespace (str): the namespace to use for this query.

        Raises:
            exceptions.BadQueryError: if the query is not parsable.
        """
        self.__app = _app

        self.__namespace = namespace

        self.__auth_domain = _auth_domain

        self.__symbols = self.TOKENIZE_REGEX.findall(query_string)
        self.__InitializeParseState()
        try:
            self.__Select()
        except exceptions.BadQueryError as error:
            raise error

    def __InitializeParseState(self):

        self._kind = None
        self._keys_only = False
        self.__projection = None
        self.__distinct = False
        self.__has_ancestor = False
        self.__offset = -1
        self.__limit = -1
        self.__hint = ""

        self.__filters = {}

        self.__orderings = []
        self.__next_symbol = 0

    def filters(self):
        """Return the compiled list of filters."""
        return self.__filters

    def hint(self):
        """Return the datastore hint.

        This is not used in NDB, but added for backwards compatibility.
        """
        return self.__hint

    def limit(self):
        """Return numerical result count limit."""
        return self.__limit

    def offset(self):
        """Return numerical result offset."""
        if self.__offset == -1:
            return 0
        else:
            return self.__offset

    def orderings(self):
        """Return the result ordering list."""
        return self.__orderings

    def is_keys_only(self):
        """Returns True if this query returns Keys, False if it returns Entities."""
        return self._keys_only

    def projection(self):
        """Returns the tuple of properties in the projection, or None."""
        return self.__projection

    def is_distinct(self):
        """Returns True if this query is marked as distinct."""
        return self.__distinct

    def kind(self):
        """Returns the kind for this query."""
        return self._kind

    @property
    def _entity(self):
        """Deprecated. Old way to refer to `kind`."""
        return self._kind

    __result_type_regex = re.compile(r"(\*|__key__)")
    __quoted_string_regex = re.compile(r"((?:\'[^\'\n\r]*\')+)")
    __ordinal_regex = re.compile(r":(\d+)$")
    __named_regex = re.compile(r":(\w+)$")
    __identifier_regex = re.compile(r"(\w+(?:\.\w+)*)$")

    __quoted_identifier_regex = re.compile(r'((?:"[^"\s]+")+)$')
    __conditions_regex = re.compile(r"(<=|>=|!=|=|<|>|is|in)$", re.IGNORECASE)
    __number_regex = re.compile(r"(\d+)$")
    __cast_regex = re.compile(
        r"(geopt|user|key|date|time|datetime)$", re.IGNORECASE
    )

    def __Error(self, error_message):
        """Generic query error.

        Args:
            error_message (str): message for the 'Parse Error' string.

        Raises:
            BadQueryError and passes on an error message from the caller. Will
                raise BadQueryError on all calls to __Error()
        """
        if self.__next_symbol >= len(self.__symbols):
            raise exceptions.BadQueryError(
                "Parse Error: %s at end of string" % error_message
            )
        else:
            raise exceptions.BadQueryError(
                "Parse Error: %s at symbol %s"
                % (error_message, self.__symbols[self.__next_symbol])
            )

    def __Accept(self, symbol_string):
        """Advance the symbol and return true if the next symbol matches input."""
        if self.__next_symbol < len(self.__symbols):
            if self.__symbols[self.__next_symbol].upper() == symbol_string:
                self.__next_symbol += 1
                return True
        return False

    def __Expect(self, symbol_string):
        """Require that the next symbol matches symbol_string, or emit an error.

        Args:
            symbol_string (str): next symbol expected by the caller

        Raises:
            BadQueryError if the next symbol doesn't match the parameter passed in.
        """
        if not self.__Accept(symbol_string):
            self.__Error("Unexpected Symbol: %s" % symbol_string)

    def __AcceptRegex(self, regex):
        """Advance and return the symbol if the next symbol matches the regex.

        Args:
            regex: the compiled regular expression to attempt acceptance on.

        Returns:
            The first group in the expression to allow for convenient access
                to simple matches. Requires () around some objects in the regex.
                None if no match is found.
        """
        if self.__next_symbol < len(self.__symbols):
            match_symbol = self.__symbols[self.__next_symbol]
            match = regex.match(match_symbol)
            if match:
                self.__next_symbol += 1
                matched_string = match.groups() and match.group(1) or None

                return matched_string

        return None

    def __AcceptTerminal(self):
        """Accept either a single semi-colon or an empty string.

        Returns:
            True

        Raises:
            BadQueryError if there are unconsumed symbols in the query.
        """

        self.__Accept(";")

        if self.__next_symbol < len(self.__symbols):
            self.__Error("Expected no additional symbols")
        return True

    def __Select(self):
        """Consume the SELECT clause and everything that follows it.

        Assumes SELECT * to start. Transitions to a FROM clause.

        Returns:
            True if parsing completed okay.
        """
        self.__Expect("SELECT")
        if self.__Accept("DISTINCT"):
            self.__distinct = True
        if not self.__Accept("*"):
            props = [self.__ExpectIdentifier()]
            while self.__Accept(","):
                props.append(self.__ExpectIdentifier())
            if props == ["__key__"]:
                self._keys_only = True
            else:
                self.__projection = tuple(props)
        return self.__From()

    def __From(self):
        """Consume the FROM clause.

        Assumes a single well formed entity in the clause.
        Assumes FROM <Entity Name>. Transitions to a WHERE clause.

        Returns:
            True: if parsing completed okay.
        """
        if self.__Accept("FROM"):
            self._kind = self.__ExpectIdentifier()
        return self.__Where()

    def __Where(self):
        """Consume the WHERE clause.

        These can have some recursion because of the AND symbol.

        Returns:
            True: if parsing the WHERE clause completed correctly, as well as
                all subsequent clauses.
        """
        if self.__Accept("WHERE"):
            return self.__FilterList()
        return self.__OrderBy()

    def __FilterList(self):
        """Consume the filter list (remainder of the WHERE clause)."""
        identifier = self.__Identifier()
        if not identifier:
            self.__Error("Invalid WHERE Identifier")

        condition = self.__AcceptRegex(self.__conditions_regex)
        if not condition:
            self.__Error("Invalid WHERE Condition")
        self.__CheckFilterSyntax(identifier, condition)

        if not self.__AddSimpleFilter(
            identifier, condition, self.__Reference()
        ):

            if not self.__AddSimpleFilter(
                identifier, condition, self.__Literal()
            ):

                type_cast = self.__TypeCast()
                if not type_cast or not self.__AddProcessedParameterFilter(
                    identifier, condition, *type_cast
                ):
                    self.__Error("Invalid WHERE Condition")

        if self.__Accept("AND"):
            return self.__FilterList()

        return self.__OrderBy()

    def __GetValueList(self):
        """Read in a list of parameters from the tokens and return the list.

        Reads in a set of tokens by consuming symbols. Only accepts literals,
        positional parameters, or named parameters.

        Returns:
            list: Values parsed from the input.
        """
        params = []

        while True:
            reference = self.__Reference()
            if reference:
                params.append(reference)
            else:
                literal = self.__Literal()
                params.append(literal)

            if not self.__Accept(","):
                break

        return params

    def __CheckFilterSyntax(self, identifier, condition):
        """Check that filter conditions are valid and throw errors if not.

        Args:
            identifier (str): identifier being used in comparison.
            condition (str): comparison operator used in the filter.
        """
        if identifier.lower() == "ancestor":
            if condition.lower() == "is":

                if self.__has_ancestor:
                    self.__Error('Only one ANCESTOR IS" clause allowed')
            else:
                self.__Error('"IS" expected to follow "ANCESTOR"')
        elif condition.lower() == "is":
            self.__Error(
                '"IS" can only be used when comparing against "ANCESTOR"'
            )

    def __AddProcessedParameterFilter(
        self, identifier, condition, operator, parameters
    ):
        """Add a filter with post-processing required.

        Args:
            identifier (str): property being compared.
            condition (str): comparison operation being used with the property
                (e.g. !=).
            operator (str): operation to perform on the parameters before
                adding the filter.
            parameters (list): list of bound parameters passed to 'operator'
                before creating the filter. When using the parameters as a
                pass-through, pass 'nop' into the operator field and the first
                value will be used unprocessed).

        Returns:
            True: if the filter was okay to add.
        """
        if parameters[0] is None:
            return False

        filter_rule = (identifier, condition)
        if identifier.lower() == "ancestor":
            self.__has_ancestor = True
            filter_rule = (self.__ANCESTOR, "is")
            assert condition.lower() == "is"

        if operator == "list" and condition.lower() != "in":
            self.__Error("Only IN can process a list of values")

        self.__filters.setdefault(filter_rule, []).append(
            (operator, parameters)
        )
        return True

    def __AddSimpleFilter(self, identifier, condition, parameter):
        """Add a filter to the query being built (no post-processing on parameter).

        Args:
            identifier (str): identifier being used in comparison.
            condition (str): comparison operator used in the filter.
            parameter (Union[str, int, Literal]: ID of the reference being made
                or a value of type Literal

        Returns:
            bool: True if the filter could be added. False otherwise.
        """
        return self.__AddProcessedParameterFilter(
            identifier, condition, "nop", [parameter]
        )

    def __Identifier(self):
        """Consume an identifier and return it.

        Returns:
            str: The identifier string. If quoted, the surrounding quotes are
                stripped.
        """
        identifier = self.__AcceptRegex(self.__identifier_regex)
        if identifier:
            if identifier.upper() in self.RESERVED_KEYWORDS:
                self.__next_symbol -= 1
                self.__Error("Identifier is a reserved keyword")
        else:
            identifier = self.__AcceptRegex(self.__quoted_identifier_regex)
            if identifier:
                identifier = identifier[1:-1].replace('""', '"')
        return identifier

    def __ExpectIdentifier(self):
        id = self.__Identifier()
        if not id:
            self.__Error("Identifier Expected")
        return id

    def __Reference(self):
        """Consume a parameter reference and return it.

        Consumes a reference to a positional parameter (:1) or a named parameter
            (:email). Only consumes a single reference (not lists).

        Returns:
            Union[str, int]: The name of the reference (integer for positional
                parameters or string for named parameters) to a bind-time
                parameter.
        """
        reference = self.__AcceptRegex(self.__ordinal_regex)
        if reference:
            return int(reference)
        else:
            reference = self.__AcceptRegex(self.__named_regex)
            if reference:
                return reference

        return None

    def __Literal(self):
        """Parse literals from our token list.

        Returns:
            Literal: The parsed literal from the input string (currently either
                a string, integer, floating point value, boolean or None).
        """

        literal = None

        if self.__next_symbol < len(self.__symbols):
            try:
                literal = int(self.__symbols[self.__next_symbol])
            except ValueError:
                pass
            else:
                self.__next_symbol += 1

            if literal is None:
                try:
                    literal = float(self.__symbols[self.__next_symbol])
                except ValueError:
                    pass
                else:
                    self.__next_symbol += 1

        if literal is None:

            literal = self.__AcceptRegex(self.__quoted_string_regex)
            if literal:
                literal = literal[1:-1].replace("''", "'")

        if literal is None:

            if self.__Accept("TRUE"):
                literal = True
            elif self.__Accept("FALSE"):
                literal = False

        if literal is not None:
            return Literal(literal)

        if self.__Accept("NULL"):
            return Literal(None)
        else:
            return None

    def __TypeCast(self, can_cast_list=True):
        """Check if the next operation is a type-cast and return the cast if so.

        Casting operators look like simple function calls on their parameters.
        This code returns the cast operator found and the list of parameters
        provided by the user to complete the cast operation.

        Args:
            can_cast_list: Boolean to determine if list can be returned as one
                of the cast operators. Default value is True.

        Returns:
            tuple: (cast operator, params) which represents the cast operation
                requested and the parameters parsed from the cast clause.
                Returns :data:None if there is no TypeCast function or list is
                not allowed to be cast.
        """
        cast_op = self.__AcceptRegex(self.__cast_regex)
        if not cast_op:
            if can_cast_list and self.__Accept("("):

                cast_op = "list"
            else:
                return None
        else:
            cast_op = cast_op.lower()
            self.__Expect("(")

        params = self.__GetValueList()
        self.__Expect(")")

        return (cast_op, params)

    def __OrderBy(self):
        """Consume the ORDER BY clause."""
        if self.__Accept("ORDER"):
            self.__Expect("BY")
            return self.__OrderList()
        return self.__Limit()

    def __OrderList(self):
        """Consume variables and sort order for ORDER BY clause."""
        identifier = self.__Identifier()
        if identifier:
            if self.__Accept("DESC"):
                self.__orderings.append((identifier, _datastore_query.DOWN))
            elif self.__Accept("ASC"):
                self.__orderings.append((identifier, _datastore_query.UP))
            else:
                self.__orderings.append((identifier, _datastore_query.UP))
        else:
            self.__Error("Invalid ORDER BY Property")

        if self.__Accept(","):
            return self.__OrderList()
        return self.__Limit()

    def __Limit(self):
        """Consume the LIMIT clause."""
        if self.__Accept("LIMIT"):

            maybe_limit = self.__AcceptRegex(self.__number_regex)

            if maybe_limit:

                if self.__Accept(","):
                    self.__offset = int(maybe_limit)
                    maybe_limit = self.__AcceptRegex(self.__number_regex)

                self.__limit = int(maybe_limit)
                if self.__limit < 1:
                    self.__Error("Bad Limit in LIMIT Value")
            else:
                self.__Error("Non-number limit in LIMIT clause")

        return self.__Offset()

    def __Offset(self):
        """Consume the OFFSET clause."""
        if self.__Accept("OFFSET"):
            if self.__offset != -1:
                self.__Error("Offset already defined in LIMIT clause")
            offset = self.__AcceptRegex(self.__number_regex)
            if offset:
                self.__offset = int(offset)
            else:
                self.__Error("Non-number offset in OFFSET clause")
        return self.__Hint()

    def __Hint(self):
        """Consume the HINT clause.

        Requires one of three options (mirroring the rest of the datastore):

        - HINT ORDER_FIRST
        - HINT ANCESTOR_FIRST
        - HINT FILTER_FIRST

        Returns:
            bool: True if the hint clause and later clauses all parsed
                correctly.
        """
        if self.__Accept("HINT"):
            if self.__Accept("ORDER_FIRST"):
                self.__hint = "ORDER_FIRST"
            elif self.__Accept("FILTER_FIRST"):
                self.__hint = "FILTER_FIRST"
            elif self.__Accept("ANCESTOR_FIRST"):
                self.__hint = "ANCESTOR_FIRST"
            else:
                self.__Error("Unknown HINT")
        return self.__AcceptTerminal()

    def _args_to_val(self, func, args):
        """Helper for GQL parsing to extract values from GQL expressions.

        This can extract the value from a GQL literal, return a Parameter
        for a GQL bound parameter (:1 or :foo), and interprets casts like
        KEY(...) and plain lists of values like (1, 2, 3).

        Args:
            func (str): A string indicating what kind of thing this is.
            args list[Union[int, str, Literal]]: One or more GQL values, each
                integer, string, or GQL literal.
        """
        vals = []
        for arg in args:
            if isinstance(arg, (int, str)):
                val = query_module.Parameter(arg)
            else:
                val = arg.Get()
            vals.append(val)
        if func == "nop":
            return vals[0]  # May be a Parameter
        pfunc = query_module.ParameterizedFunction(func, vals)
        return pfunc

    def query_filters(self, model_class, filters):
        """Get the filters in a format compatible with the Query constructor"""
        gql_filters = self.filters()
        for name_op in sorted(gql_filters):
            name, op = name_op
            values = gql_filters[name_op]
            op = op.lower()
            for (func, args) in values:
                prop = model_class._properties.get(name)
                val = self._args_to_val(func, args)
                if isinstance(val, query_module.ParameterizedThing):
                    node = query_module.ParameterNode(prop, op, val)
                else:
                    node = prop._comparison(op, val)
                filters.append(node)
        if filters:
            filters = query_module.ConjunctionNode(*filters)
        else:
            filters = None
        return filters

    def get_query(self):
        """Create and return a Query instance.

        Returns:
            google.cloud.ndb.query.Query: A new query with values extracted
                from the processed GQL query string.
        """
        kind = self.kind()
        if kind is None:
            model_class = model.Model
        else:
            model_class = model.Model._lookup_model(kind)
            kind = model_class._get_kind()
        ancestor = None
        model_filters = list(model_class._default_filters())
        filters = self.query_filters(model_class, model_filters)
        offset = self.offset()
        limit = self.limit()
        if limit < 0:
            limit = None
        keys_only = self.is_keys_only()
        if not keys_only:
            keys_only = None
        default_options = query_module.QueryOptions(
            offset=offset, limit=limit, keys_only=keys_only
        )
        projection = self.projection()
        project = self.__app
        namespace = self.__namespace
        if self.is_distinct():
            distinct_on = projection
        else:
            distinct_on = None
        order_by = []
        for order in self.orderings():
            order_str, direction = order
            if direction == 2:
                order_str = "-{}".format(order_str)
            order_by.append(order_str)
        return query_module.Query(
            kind=kind,
            ancestor=ancestor,
            filters=filters,
            order_by=order_by,
            project=project,
            namespace=namespace,
            default_options=default_options,
            projection=projection,
            distinct_on=distinct_on,
        )


class Literal(object):
    """Class for representing literal values differently than unbound params.
    This is a simple wrapper class around basic types and datastore types.
    """

    def __init__(self, value):
        self.__value = value

    def Get(self):
        """Return the value of the literal."""
        return self.__value

    def __eq__(self, other):
        """A literal is equal to another if their values are the same"""
        if not isinstance(other, Literal):
            return NotImplemented
        return self.Get() == other.Get()

    def __repr__(self):
        return "Literal(%s)" % repr(self.__value)
