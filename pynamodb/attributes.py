# pynamodb/attributes.py
import base64
import calendar
import collections.abc
import json
import time
import warnings
from base64 import b64encode, b64decode
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from inspect import getfullargspec
from inspect import getmembers
from typing import Any, Callable, Dict, Generic, List, Mapping, Optional, TypeVar, Type, Union, Set, overload, Iterable
from typing import TYPE_CHECKING

from pynamodb._util import attr_value_to_simple_dict
from pynamodb._util import bin_decode_attr
from pynamodb._util import bin_encode_attr
from pynamodb._util import simple_dict_to_attr_value
from pynamodb.constants import BINARY, BINARY_SET, BOOLEAN, DATETIME_FORMAT, LIST, MAP, NULL, NUMBER, NUMBER_SET, STRING, STRING_SET
from pynamodb.exceptions import AttributeDeserializationError, AttributeNullError, TypeMismatchException, NoneValueException
from pynamodb.expressions.operand import Path

if TYPE_CHECKING:
    from pynamodb.expressions.condition import (
        BeginsWith, Between, Comparison, Contains, NotExists, Exists, In
    )
    from pynamodb.expressions.operand import (
        _Decrement, _IfNotExists, _Increment, _ListAppend
    )
    from pynamodb.expressions.update import (
        AddAction, DeleteAction, RemoveAction, SetAction
    )

_T = TypeVar('_T')
_KT = TypeVar('_KT', bound=str)
_VT = TypeVar('_VT')
_MT = TypeVar('_MT', bound='MapAttribute')
_ACT = TypeVar('_ACT', bound='AttributeContainer')
_A = TypeVar('_A', bound='Attribute')

_IMMUTABLE_TYPES = (str, int, float, datetime, timedelta, bytes, bool, tuple, frozenset, type(None))
_IMMUTABLE_TYPE_NAMES = ', '.join(map(lambda x: x.__name__, _IMMUTABLE_TYPES))

class Attribute(Generic[_T]):
    attr_type: str
    null = False

    def __init__(
        self,
        hash_key: bool = False,
        range_key: bool = False,
        null: Optional[bool] = None,
        default: Optional[Union[_T, Callable[..., _T]]] = None,
        default_for_new: Optional[Union[Any, Callable[..., _T]]] = None,
        attr_name: Optional[str] = None,
    ) -> None:
        if default is not None and default_for_new is not None:
            raise ValueError("An attribute cannot have both default and default_for_new parameters")
        if not callable(default) and not isinstance(default, _IMMUTABLE_TYPES):
            raise ValueError(
                f"An attribute's 'default' must be immutable ({_IMMUTABLE_TYPE_NAMES}) or a callable "
                "(see https://pynamodb.readthedocs.io/en/latest/api.html#pynamodb.attributes.Attribute)"
            )
        if not callable(default_for_new) and not isinstance(default_for_new, _IMMUTABLE_TYPES):
            raise ValueError(
                f"An attribute's 'default_for_new' must be immutable ({_IMMUTABLE_TYPE_NAMES}) or a callable "
                "(see https://pynamodb.readthedocs.io/en/latest/api.html#pynamodb.attributes.Attribute)"
            )
        self.default = default
        self.default_for_new = default_for_new
        if null is not None:
            self.null = null
        self.is_hash_key = hash_key
        self.is_range_key = range_key
        self.attr_path: List[str] = [attr_name]  # type: ignore

    @property
    def attr_name(self) -> str:
        return self.attr_path[-1]

    @attr_name.setter
    def attr_name(self, value: str) -> None:
        self.attr_path[-1] = value

    def __set__(self, instance: Any, value: Optional[_T]) -> None:
        if instance and not self._is_map_attribute_class_object(instance):
            attr_name = instance._dynamo_to_python_attrs.get(self.attr_name, self.attr_name)
            instance.attribute_values[attr_name] = value

    @overload
    def __get__(self: _A, instance: None, owner: Any) -> _A: ...
    @overload
    def __get__(self: _A, instance: Any, owner: Any) -> _T: ...
    def __get__(self: _A, instance: Any, owner: Any) -> Union[_A, _T]:
        if self._is_map_attribute_class_object(instance):
            attr_name = instance._dynamo_to_python_attrs.get(self.attr_name, self.attr_name)
            return instance.__dict__.get(attr_name, None) or self
        elif instance:
            attr_name = instance._dynamo_to_python_attrs.get(self.attr_name, self.attr_name)
            return instance.attribute_values.get(attr_name, None)
        else:
            return self

    def __set_name__(self, owner: Type[Any], name: str) -> None:
        self.attr_name = self.attr_name or name

    def _is_map_attribute_class_object(self, instance: 'Attribute') -> bool:
        return isinstance(instance, MapAttribute) and not instance._is_attribute_container()

    def serialize(self, value: Any) -> Any:
        return value

    def deserialize(self, value: Any) -> Any:
        return value

    def get_value(self, value: Dict[str, Any]) -> Any:
        if self.attr_type not in value:
            raise AttributeDeserializationError(self.attr_name, self.attr_type)
        return value[self.attr_type]

    def __iter__(self):
        raise TypeError("'{}' object is not iterable".format(self.__class__.__name__))

    def __eq__(self, other: Any) -> 'Comparison':
        return Path(self).__eq__(other)

    def __ne__(self, other: Any) -> 'Comparison':
        return Path(self).__ne__(other)

    def __lt__(self, other: Any) -> 'Comparison':
        return Path(self).__lt__(other)

    def __le__(self, other: Any) -> 'Comparison':
        return Path(self).__le__(other)

    def __gt__(self, other: Any) -> 'Comparison':
        return Path(self).__gt__(other)

    def __ge__(self, other: Any) -> 'Comparison':
        return Path(self).__ge__(other)

    def __getitem__(self, item: Union[int, str]) -> Path:
        return Path(self).__getitem__(item)

    def between(self, lower: Any, upper: Any) -> 'Between':
        return Path(self).between(lower, upper)

    def is_in(self, *values: _T) -> 'In':
        return Path(self).is_in(*values)

    def exists(self) -> 'Exists':
        return Path(self).exists()

    def does_not_exist(self) -> 'NotExists':
        return Path(self).does_not_exist()

    def is_type(self):
        return Path(self).is_type(self.attr_type)

    def startswith(self, prefix: str) -> 'BeginsWith':
        return Path(self).startswith(prefix)

    def contains(self, item: Any) -> 'Contains':
        return Path(self).contains(item)

    def __add__(self, other: Any) -> '_Increment':
        return Path(self).__add__(other)

    def __radd__(self, other: Any) -> '_Increment':
        return Path(self).__radd__(other)

    def __sub__(self, other: Any) -> '_Decrement':
        return Path(self).__sub__(other)

    def __rsub__(self, other: Any) -> '_Decrement':
        return Path(self).__rsub__(other)

    def __or__(self, other: Any) -> '_IfNotExists':
        return Path(self).__or__(other)

    def append(self, other: Iterable) -> '_ListAppend':
        return Path(self).append(other)

    def prepend(self, other: Iterable) -> '_ListAppend':
        return Path(self).prepend(other)

    def set(
        self,
        value: Union[_T, 'Attribute[_T]', '_Increment', '_Decrement', '_IfNotExists', '_ListAppend']
    ) -> Union['SetAction', 'RemoveAction']:
        return Path(self).set(value)

    def remove(self) -> 'RemoveAction':
        return Path(self).remove()

    def add(self, *values: Any) -> 'AddAction':
        return Path(self).add(*values)

    def delete(self, *values: Any) -> 'DeleteAction':
        return Path(self).delete(*values)

class AttributeContainerMeta(type):
    _attributes: Dict[str, Attribute]

    def __new__(cls, name, bases, namespace, discriminator=None):
        return super().__new__(cls, name, bases, namespace)

    def __init__(self, name, bases, namespace, discriminator=None):
        super().__init__(name, bases, namespace)
        AttributeContainerMeta._initialize_attributes(self, discriminator)

    @staticmethod
    def _initialize_attributes(cls, discriminator_value):
        cls._attributes = {}
        cls._dynamo_to_python_attrs = {}
        for name, attribute in getmembers(cls, lambda o: isinstance(o, Attribute)):
            cls._attributes[name] = attribute
            if attribute.attr_name != name:
                cls._dynamo_to_python_attrs[attribute.attr_name] = name
        discriminators = [name for name, attr in cls._attributes.items() if isinstance(attr, DiscriminatorAttribute)]
        if len(discriminators) > 1:
            raise ValueError("{} has more than one discriminator attribute: {}".format(
                cls.__name__, ", ".join(discriminators)))
        cls._discriminator = discriminators[0] if discriminators else None
        if discriminator_value is not None:
            if not cls._discriminator:
                raise ValueError("{} does not have a discriminator attribute".format(cls.__name__))
            cls._attributes[cls._discriminator].register_class(cls, discriminator_value)

class AttributeContainer(metaclass=AttributeContainerMeta):
    def __init__(self, _user_instantiated: bool = True, **attributes: Attribute) -> None:
        self.attribute_values: Dict[str, Any] = {}
        self._set_discriminator()
        self._set_defaults(_user_instantiated=_user_instantiated)
        self._set_attributes(**attributes)

    @classmethod
    def _get_attributes(cls) -> Dict[str, Attribute]:
        warnings.warn("`Model._get_attributes` is deprecated in favor of `Model.get_attributes` now")
        return cls.get_attributes()

    @classmethod
    def get_attributes(cls) -> Dict[str, Attribute]:
        return cls._attributes

    @classmethod
    def _dynamo_to_python_attr(cls, dynamo_key: str) -> str:
        return cls._dynamo_to_python_attrs.get(dynamo_key, dynamo_key)

    @classmethod
    def _get_discriminator_attribute(cls) -> Optional['DiscriminatorAttribute']:
        return cls.get_attributes()[cls._discriminator] if cls._discriminator else None

    def _set_discriminator(self) -> None:
        discriminator_attr = self._get_discriminator_attribute()
        if discriminator_attr and discriminator_attr.get_discriminator(self.__class__) is not None:
            setattr(self, self._discriminator, self.__class__)

    def _set_defaults(self, _user_instantiated: bool = True) -> None:
        for name, attr in self.get_attributes().items():
            if _user_instantiated and attr.default_for_new is not None:
                default = attr.default_for_new
            else:
                default = attr.default
            if callable(default):
                value = default()
            else:
                value = default
            if value is not None:
                setattr(self, name, value)

    def _set_attributes(self, **attributes: Attribute) -> None:
        for attr_name, attr_value in attributes.items():
            if attr_name not in self.get_attributes():
                raise ValueError("Attribute {} specified does not exist".format(attr_name))
            setattr(self, attr_name, attr_value)

    def _container_serialize(self, null_check: bool = True) -> Dict[str, Dict[str, Any]]:
        attribute_values: Dict[str, Dict[str, Any]] = {}
        for name, attr in self.get_attributes().items():
            value = getattr(self, name)
            try:
                if isinstance(value, MapAttribute) and not value.validate(null_check=null_check):
                    raise ValueError("Attribute '{}' is not correctly typed".format(name))
                if value is not None:
                    if isinstance(attr, (ListAttribute, MapAttribute)):
                        attr_value = attr.serialize(value, null_check=null_check)
                    else:
                        attr_value = attr.serialize(value)
                else:
                    attr_value = None
            except AttributeNullError as e:
                e.prepend_path(name)
                raise
            if null_check and attr_value is None and not attr.null:
                raise AttributeNullError(name)
            if attr_value is not None:
                attribute_values[attr.attr_name] = {attr.attr_type: attr_value}
        return attribute_values

    def _container_deserialize(self, attribute_values: Dict[str, Dict[str, Any]]) -> None:
        self.attribute_values = {}
        self._set_discriminator()
        self._set_defaults(_user_instantiated=False)
        for name, attr in self.get_attributes().items():
            attribute_value = attribute_values.get(attr.attr_name)
            if attribute_value and NULL not in attribute_value:
                value = attr.deserialize(attr.get_value(attribute_value))
                setattr(self, name, value)

    @classmethod
    def _update_attribute_types(cls, attribute_values: Dict[str, Dict[str, Any]]):
        for attr in cls.get_attributes().values():
            attribute_value = attribute_values.get(attr.attr_name)
            if attribute_value:
                AttributeContainer._coerce_attribute_type(attr.attr_type, attribute_value)
                if isinstance(attr, ListAttribute) and attr.element_type and LIST in attribute_value:
                    if issubclass(attr.element_type, AttributeContainer):
                        for element in attribute_value[LIST]:
                            if MAP in element:
                                attr.element_type._update_attribute_types(element[MAP])
                    else:
                        for element in attribute_value[LIST]:
                            AttributeContainer._coerce_attribute_type(attr.element_type.attr_type, element)
                if isinstance(attr, AttributeContainer) and MAP in attribute_value:
                    attr._update_attribute_types(attribute_value[MAP])

    @staticmethod
    def _coerce_attribute_type(attr_type: str, attribute_value: Dict[str, Any]):
        if attr_type == BINARY and STRING in attribute_value:
            attribute_value[BINARY] = base64.b64decode(attribute_value.pop(STRING))
        elif attr_type == BINARY_SET and LIST in attribute_value:
            attribute_value[BINARY_SET] = [base64.b64decode(v[STRING]) for v in attribute_value.pop(LIST)]
        elif attr_type in {NUMBER_SET, STRING_SET} and LIST in attribute_value:
            json_type = NUMBER if attr_type == NUMBER_SET else STRING
            if all(next(iter(v)) == json_type for v in attribute_value[LIST]):
                attribute_value[attr_type] = [value[json_type] for value in attribute_value.pop(LIST)]

    @classmethod
    def _get_discriminator_class(cls, attribute_values: Dict[str, Dict[str, Any]]) -> Optional[Type]:
        discriminator_attr = cls._get_discriminator_attribute()
        if discriminator_attr:
            discriminator_attribute_value = attribute_values.get(discriminator_attr.attr_name, None)
            if discriminator_attribute_value:
                discriminator_value = discriminator_attr.get_value(discriminator_attribute_value)
                return discriminator_attr.deserialize(discriminator_value)
        return None

    @classmethod
    def _instantiate(cls: Type[_ACT], attribute_values: Dict[str, Dict[str, Any]]) -> _ACT:
        stored_cls = cls._get_discriminator_class(attribute_values)
        if stored_cls and not issubclass(stored_cls, cls):
            raise ValueError("Cannot instantiate a {} from the returned class: {}".format(
                cls.__name__, stored_cls.__name__))
        instance = (stored_cls or cls)(_user_instantiated=False)
        AttributeContainer._container_deserialize(instance, attribute_values)
        return instance

    def to_dynamodb_dict(self) -> Dict[str, Dict[str, Any]]:
        attr_values = self._container_serialize(null_check=False)
        for v in attr_values.values():
            bin_encode_attr(v)
        return attr_values

    def from_dynamodb_dict(self, d: Dict[str, Dict[str, Any]]) -> None:
        for v in d.values():
            bin_decode_attr(v)
        self._update_attribute_types(d)
        self._container_deserialize(d)

    def to_simple_dict(self, *, force: bool = False) -> Dict[str, Any]:
        return {k: attr_value_to_simple_dict(v, force) for k, v in self._container_serialize(null_check=False).items()}

    def from_simple_dict(self, d: Dict[str, Any]) -> None:
        attribute_values = {k: simple_dict_to_attr_value(v) for k, v in d.items()}
        self._update_attribute_types(attribute_values)
        self._container_deserialize(attribute_values)

    def __repr__(self) -> str:
        fields = ', '.join(f'{k}={v!r}' for k, v in self.attribute_values.items())
        return f'{type(self).__name__}({fields})'

class DiscriminatorAttribute(Attribute[type]):
    attr_type = STRING

    def __init__(self, attr_name: Optional[str] = None) -> None:
        super().__init__(attr_name=attr_name)
        self._class_map: Dict[type, Any] = {}
        self._discriminator_map: Dict[Any, type] = {}

    def register_class(self, cls: type, discriminator: Any):
        discriminator = discriminator(cls) if callable(discriminator) else discriminator
        current_class = self._discriminator_map.get(discriminator)
        if current_class and current_class != cls:
            raise ValueError("The discriminator value '{}' is already assigned to a class: {}".format(
                discriminator, current_class.__name__))
        if cls not in self._class_map:
            self._class_map[cls] = discriminator
        self._discriminator_map[discriminator] = cls

    def get_registered_subclasses(self, cls: Type[_T]) -> List[Type[_T]]:
        return [k for k in self._class_map.keys() if issubclass(k, cls)]

    def get_discriminator(self, cls: type) -> Optional[Any]:
        return self._class_map.get(cls)

    def __set__(self, instance: Any, value: Optional[type]) -> None:
        if type(instance) != value:
            raise ValueError("The discriminator attribute must be set to the instance type: {}".format(type(instance)))
        super().__set__(instance, value)

    def serialize(self, value):
        return self._class_map[value]

    def deserialize(self, value):
        if value not in self._discriminator_map:
            raise ValueError("Unknown discriminator value: {}".format(value))
        return self._discriminator_map[value]

class BinaryAttribute(Attribute[bytes]):
    attr_type = BINARY

    def __init__(self, *args: Any, legacy_encoding: bool, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.legacy_encoding = legacy_encoding

    def serialize(self, value):
        if self.legacy_encoding:
            return b64encode(value)
        return value

    def deserialize(self, value):
        if self.legacy_encoding:
            return b64decode(value)
        return value

class BinarySetAttribute(Attribute[Set[bytes]]):
    attr_type = BINARY_SET
    null = True

    def __init__(self, *args: Any, legacy_encoding: bool, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.legacy_encoding = legacy_encoding

    def serialize(self, value):
        if self.legacy_encoding:
            return [b64encode(v) for v in value] or None
        return list(value) or None

    def deserialize(self, value):
        if self.legacy_encoding:
            return {b64decode(v) for v in value}
        return set(value)

class UnicodeAttribute(Attribute[str]):
    attr_type = STRING

class UnicodeSetAttribute(Attribute[Set[str]]):
    attr_type = STRING_SET
    null = True

    def serialize(self, value):
        return list(value) or None

    def deserialize(self, value):
        return set(value)

class JSONAttribute(Attribute[Any]):
    attr_type = STRING

    def serialize(self, value) -> Optional[str]:
        if value is None:
            return None
        encoded = json.dumps(value)
        return encoded

    def deserialize(self, value):
        return json.loads(value, strict=False)

class BooleanAttribute(Attribute[bool]):
    attr_type = BOOLEAN

    def serialize(self, value):
        if value is None:
            return None
        elif value:
            return True
        else:
            return False

    def deserialize(self, value):
        return bool(value)

class NumberAttribute(Attribute[float]):
    attr_type = NUMBER

    def serialize(self, value):
        return json.dumps(value)

    def deserialize(self, value):
        return json.loads(value)

class NumberSetAttribute(Attribute[Set[float]]):
    attr_type = NUMBER_SET
    null = True

    def serialize(self, value):
        return [json.dumps(v) for v in value] or None

    def deserialize(self, value):
        return {json.loads(v) for v in value}

class VersionAttribute(NumberAttribute):
    null = True

    def __set__(self, instance, value):
        super().__set__(instance, int(value))

    def __get__(self, instance, owner):
        val = super().__get__(instance, owner)
        return int(val) if isinstance(val, float) else val

    def serialize(self, value):
        return super().serialize(int(value))

    def deserialize(self, value):
        return int(super().deserialize(value))

class TTLAttribute(Attribute[datetime]):
    attr_type = NUMBER

    def _normalize(self, value):
        if value is None:
            return
        if isinstance(value, timedelta):
            value = int(time.time() + value.total_seconds())
        elif isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValueError("datetime must be timezone-aware")
            value = calendar.timegm(value.utctimetuple())
        else:
            raise ValueError("TTLAttribute value must be a timedelta or datetime")
        return datetime.fromtimestamp(value, tz=timezone.utc)

    def __set__(self, instance, value):
        super().__set__(instance, self._normalize(value))

    def serialize(self, value):
        if value is None:
            return None
        return json.dumps(calendar.timegm(self._normalize(value).utctimetuple()))

    def deserialize(self, value):
        timestamp = json.loads(value)
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

class UTCDateTimeAttribute(Attribute[datetime]):
    attr_type = STRING

    def serialize(self, value):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        fmt = value.astimezone(timezone.utc).strftime(DATETIME_FORMAT).zfill(31)
        return fmt

    def deserialize(self, value):
        return self._fast_parse_utc_date_string(value)

    @staticmethod
    def _fast_parse_utc_date_string(date_string: str) -> datetime:
        _int = int
        try:
            date_string = date_string.zfill(31)
            if (len(date_string) != 31 or date_string[4] != '-' or date_string[7] != '-'
                    or date_string[10] != 'T' or date_string[13] != ':' or date_string[16] != ':'
                    or date_string[19] != '.' or date_string[26:31] != '+0000'):
                raise ValueError("Datetime string '{}' does not match format '{}'".format(date_string, DATETIME_FORMAT))
            return datetime(
                _int(date_string[0:4]), _int(date_string[5:7]), _int(date_string[8:10]),
                _int(date_string[11:13]), _int(date_string[14:16]), _int(date_string[17:19]),
                _int(date_string[20:26]), timezone.utc
            )
        except (TypeError, ValueError):
            raise ValueError("Datetime string '{}' does not match format '{}'".format(date_string, DATETIME_FORMAT))

class NullAttribute(Attribute[None]):
    attr_type = NULL

    def serialize(self, value):
        return True

    def deserialize(self, value):
        return None

class MetaMapAttribute(AttributeContainerMeta):
    def __init__(self, name, bases, namespace, discriminator=None):
        super().__init__(name, bases, namespace, discriminator=discriminator)
        for attr_name, attr in self._attributes.items():
            if isinstance(attr, (BinaryAttribute, BinarySetAttribute)) and attr.legacy_encoding:
                raise ValueError(
                    "Legacy encoding is only ever needed for top-level (model) attributes. "
                    f"Please remove the legacy_encoding flag from the definition of '{attr_name}'."
                )

class MapAttribute(Attribute[Mapping[_KT, _VT]], AttributeContainer, metaclass=MetaMapAttribute):
    attr_type = MAP
    attribute_args = getfullargspec(Attribute.__init__).args[1:]

    def __init__(self, required_keys: Optional[Dict[str, Attribute]] = None, **attributes):
        self.attribute_kwargs = {arg: attributes.pop(arg) for arg in self.attribute_args if arg in attributes}
        self.required_keys = required_keys or {}
        AttributeContainer.__init__(self, **attributes)
        if self.attribute_kwargs and (
                attributes or self.is_raw() or all(arg in self.get_attributes() for arg in self.attribute_kwargs)):
            self._set_attributes(**self.attribute_kwargs)

    def _is_attribute_container(self):
        return 'attribute_values' in self.__dict__

    def _make_attribute(self):
        if not self._is_attribute_container():
            raise AssertionError("MapAttribute._make_attribute called on an initialized instance")
        kwargs = self.attribute_kwargs
        del self.attribute_kwargs
        del self.attribute_values
        Attribute.__init__(self, **kwargs)
        for name, attr in self.get_attributes().items():
            self.__dict__[name] = deepcopy(attr)

    def _update_attribute_paths(self, path_segment):
        if self._is_attribute_container():
            raise AssertionError("MapAttribute._update_attribute_paths called before MapAttribute._make_attribute")
        for name in self.get_attributes().keys():
            local_attr = self.__dict__[name]
            local_attr.attr_path.insert(0, path_segment)
            if isinstance(local_attr, MapAttribute):
                local_attr._update_attribute_paths(path_segment)

    def __eq__(self, other: Any) -> 'Comparison':
        if self._is_attribute_container():
            return NotImplemented
        return Attribute.__eq__(self, other)

    def __ne__(self, other: Any) -> 'Comparison':
        if self._is_attribute_container():
            return NotImplemented
        return Attribute.__ne__(self, other)

    def __lt__(self, other: Any) -> 'Comparison':
        if self._is_attribute_container():
            return NotImplemented
        return Attribute.__lt__(self, other)

    def __le__(self, other: Any) -> 'Comparison':
        if self._is_attribute_container():
            return NotImplemented
        return Attribute.__le__(self, other)

    def __gt__(self, other: Any) -> 'Comparison':
        if self._is_attribute_container():
            return NotImplemented
        return Attribute.__gt__(self, other)

    def __ge__(self, other: Any) -> 'Comparison':
        if self._is_attribute_container():
            return NotImplemented
        return Attribute.__ge__(self, other)

    def __iter__(self):
        if self._is_attribute_container():
            return iter(self.attribute_values)
        return super().__iter__()

    def __getitem__(self, item: _KT) -> _VT:
        if self._is_attribute_container():
            return self.attribute_values[item]
        if item in self.get_attributes():
            return getattr(self, item)
        elif self.is_raw():
            return Path(self.attr_path + [str(item)])
        else:
            raise AttributeError("'{}' has no attribute '{}'".format(self.__class__.__name__, item))

    def __setitem__(self, item, value):
        if not self._is_attribute_container():
            raise TypeError("'{}' object does not support item assignment".format(self.__class__.__name__))
        if item in self.get_attributes():
            setattr(self, item, value)
        elif self.is_raw():
            self.attribute_values[item] = value
        else:
            raise AttributeError("'{}' has no attribute '{}'".format(self.__class__.__name__, item))

    def __getattr__(self, attr: str) -> _VT:
        if self.is_raw() and self._is_attribute_container():
            try:
                return self.attribute_values[attr]
            except KeyError:
                pass
        raise AttributeError("'{}' has no attribute '{}'".format(self.__class__.__name__, attr))

    @overload
    def __get__(self: _A, instance: None, owner: Any) -> _A: ...
    @overload
    def __get__(self: _MT, instance: Any, owner: Any) -> _MT: ...
    def __get__(self: _A, instance: Any, owner: Any) -> Union[_A, _T]:
        return super().__get__(instance, owner)

    def __setattr__(self, name, value):
        if self.is_raw() and self._is_attribute_container():
            self.attribute_values[name] = value
        else:
            object.__setattr__(self, name, value)

    def __set__(self, instance: Any, value: Union[None, 'MapAttribute[_KT, _VT]', Mapping[_KT, _VT]]):
        if isinstance(value, collections.abc.Mapping):
            value = type(self)(**value)
        return super().__set__(instance, value)

    def __set_name__(self, owner: Type[Any], name: str) -> None:
        if issubclass(owner, AttributeContainer):
            self._make_attribute()
            super().__set_name__(owner, name)
            self._update_attribute_paths(self.attr_name)

            def _set_attributes(self, **attrs):
        if self.is_raw():
            for name, value in attrs.items():
                setattr(self, name, value)
        else:
            super()._set_attributes(**attrs)

    def is_correctly_typed(self, key, attr, *, null_check: bool = True):
        can_be_null = attr.null or not null_check
        value = getattr(self, key)
        if can_be_null and value is None:
            return True
        if value is None:
            raise AttributeNullError(key)

        # Check required keys for MapAttribute
        if hasattr(attr, 'required_keys') and attr.required_keys:
            for required_key in attr.required_keys:
                if not hasattr(value, required_key) or getattr(value, required_key) is None:
                    exception = NoneValueException(f"{key}.{required_key}")
                    raise exception

        # Type checking
        if hasattr(attr, 'attr_type'):
            if attr.attr_type == 'S' and not isinstance(value, str):
                raise TypeMismatchError(key, 'UnicodeAttribute', type(value).__name__)
            elif attr.attr_type == 'N' and not isinstance(value, (int, float)):
                raise TypeMismatchError(key, 'NumberAttribute', type(value).__name__)
            elif attr.attr_type == 'B' and not isinstance(value, bytes):
                raise TypeMismatchError(key, 'BinaryAttribute', type(value).__name__)
            elif attr.attr_type == 'BOOL' and not isinstance(value, bool):
                raise TypeMismatchError(key, 'BooleanAttribute', type(value).__name__)

        # For MapAttribute, check each attribute inside it
        if hasattr(value, 'attribute_values') and hasattr(value, 'get_attributes'):
            attributes = value.get_attributes()
            for attr_key, attr_obj in attributes.items():
                if hasattr(value, attr_key):
                    try:
                        nested_value = getattr(value, attr_key)
                        if nested_value is not None or not attr_obj.null:
                            value.is_correctly_typed(attr_key, attr_obj, null_check=null_check)
                    except (AttributeNullError, TypeMismatchError, NoneValueException) as e:
                        if hasattr(e, 'prepend_path'):
                            e.prepend_path(key)
                        raise

        return True

        # Check required keys for MapAttribute
        if hasattr(attr, 'required_keys') and attr.required_keys:
            for required_key in attr.required_keys:
                if not hasattr(value, required_key) or getattr(value, required_key) is None:
                    exception = NoneValueException(f"{key}.{required_key}")
                    raise exception

        # Type checking
        if hasattr(attr, 'attr_type'):
            if attr.attr_type == 'S' and not isinstance(value, str):
                raise TypeMismatchError(key, 'UnicodeAttribute', type(value).__name__)
            elif attr.attr_type == 'N' and not isinstance(value, (int, float)):
                raise TypeMismatchError(key, 'NumberAttribute', type(value).__name__)
            elif attr.attr_type == 'B' and not isinstance(value, bytes):
                raise TypeMismatchError(key, 'BinaryAttribute', type(value).__name__)
            elif attr.attr_type == 'BOOL' and not isinstance(value, bool):
                raise TypeMismatchError(key, 'BooleanAttribute', type(value).__name__)

        # For MapAttribute, check each attribute inside it
        if hasattr(value, 'attribute_values') and hasattr(value, 'get_attributes'):
            attributes = value.get_attributes()
            for attr_key, attr_obj in attributes.items():
                if hasattr(value, attr_key):
                    try:
                        nested_value = getattr(value, attr_key)
                        if nested_value is not None or not attr_obj.null:
                            value.is_correctly_typed(attr_key, attr_obj, null_check=null_check)
                    except (AttributeNullError, TypeMismatchError, NoneValueException) as e:
                        if hasattr(e, 'prepend_path'):
                            e.prepend_path(key)
                        raise

        return True
        if hasattr(attr, 'attr_type'):
            if attr.attr_type == 'S' and not isinstance(value, str):
                raise TypeMismatchError(key, 'UnicodeAttribute', type(value).__name__)
            elif attr.attr_type == 'N' and not isinstance(value, (int, float)):
                raise TypeMismatchError(key, 'NumberAttribute', type(value).__name__)
            elif attr.attr_type == 'B' and not isinstance(value, bytes):
                raise TypeMismatchError(key, 'BinaryAttribute', type(value).__name__)
            elif attr.attr_type == 'BOOL' and not isinstance(value, bool):
                raise TypeMismatchError(key, 'BooleanAttribute', type(value).__name__)
        return True
        if hasattr(attr, 'attr_type'):
            if attr.attr_type == 'S' and not isinstance(value, str):
                raise TypeMismatchException(key, UnicodeAttribute, type(_get_class_for_serialize(value)))
            elif attr.attr_type == 'N' and not isinstance(value, (int, float)):
                raise TypeMismatchException(key, NumberAttribute, type(_get_class_for_serialize(value)))
            elif attr.attr_type == 'B' and not isinstance(value, bytes):
                raise TypeMismatchException(key, BinaryAttribute, type(_get_class_for_serialize(value)))
            elif attr.attr_type == 'BOOL' and not isinstance(value, bool):
                raise TypeMismatchException(key, BooleanAttribute, type(_get_class_for_serialize(value)))
            elif attr.attr_type in ('SS', 'NS', 'BS') and not isinstance(value, (set, list, tuple)):
                raise TypeMismatchException(key, type(attr), type(_get_class_for_serialize(value)))
            elif attr.attr_type == 'L' and not isinstance(value, (list, tuple)):
                raise TypeMismatchException(key, ListAttribute, type(_get_class_for_serialize(value)))
        return True

    def validate(self, *, null_check: bool = True):
        is_valid = True
        for k, v in self.get_attributes().items():
            try:
                is_valid = is_valid and self.is_correctly_typed(k, v, null_check=null_check)
                if is_valid and isinstance(v, MapAttribute) and hasattr(getattr(self, k), 'validate'):
                    nested_value = getattr(self, k)
                    if nested_value is not None:
                        try:
                            nested_value.validate(null_check=null_check)
                        except (AttributeNullError, TypeMismatchException) as e:
                            e.prepend_path(k)
                            raise
            except AttributeNullError as e:
                if hasattr(e, 'prepend_path'):
                    e.prepend_path(k)
                raise
            except TypeMismatchException as e:
                if hasattr(e, 'prepend_path'):
                    e.prepend_path(k)
                raise
        return is_valid

    def _serialize_undeclared_attributes(self, values, container: Dict):
        for attr_name in values:
            if attr_name not in self.get_attributes():
                v = values[attr_name]
                attr_class = _get_class_for_serialize(v)
                attr_type = attr_class.attr_type
                attr_value = attr_class.serialize(v)
                if attr_value is None:
                    attr_type = NULL
                    attr_value = True
                container[attr_name] = {attr_type: attr_value}
        return container

    def serialize(self, values, *, null_check: bool = True):
        if self.required_keys:
            for key, expected_attr in self.required_keys.items():
                if key not in values or values[key] is None:
                    raise NoneValueException(key)
                actual_attr = _get_class_for_serialize(values[key])
                if not isinstance(actual_attr, type(expected_attr)):
                    raise TypeMismatchException(key, type(expected_attr), type(actual_attr))
                try:
                    serialized_value = expected_attr.serialize(values[key])
                    if serialized_value is None and not expected_attr.null:
                        raise NoneValueException(key)
                    values[key] = serialized_value
                except AttributeNullError:
                    raise NoneValueException(key)

        if not self.is_raw():
            if not isinstance(values, type(self)):
                instance = type(self)()
                instance.attribute_values = {}
                for name in values:
                    if name in self.get_attributes():
                        setattr(instance, name, values[name])
                values = instance
            values.validate(null_check=null_check)
            return AttributeContainer._container_serialize(values, null_check=null_check)
        return self._serialize_undeclared_attributes(values, {})

    def deserialize(self, values):
        if not self.is_raw():
            return self._instantiate(values)
        return {
            k: DESERIALIZE_CLASS_MAP[attr_type].deserialize(attr_value)
            for k, v in values.items() for attr_type, attr_value in v.items()
        }

    @classmethod
    def is_raw(cls):
        return cls == MapAttribute

    def as_dict(self):
        result = {}
        for key, value in self.attribute_values.items():
            result[key] = value.as_dict() if isinstance(value, MapAttribute) else value
        return result

class DynamicMapAttribute(MapAttribute):
    def __setattr__(self, name, value):
        if name in self.get_attributes():
            object.__setattr__(self, name, value)
        else:
            super().__setattr__(name, value)

    def serialize(self, values, *, null_check: bool = True):
        if self.required_keys:
            for key, expected_attr in self.required_keys.items():
                if key not in values or values[key] is None:
                    raise NoneValueException(key)
                actual_attr = _get_class_for_serialize(values[key])
                if not isinstance(actual_attr, type(expected_attr)):
                    raise TypeMismatchException(key, type(expected_attr), type(actual_attr))
                try:
                    serialized_value = expected_attr.serialize(values[key])
                    if serialized_value is None and not expected_attr.null:
                        raise NoneValueException(key)
                    values[key] = serialized_value
                except AttributeNullError:
                    raise NoneValueException(key)

        if not isinstance(values, type(self)):
            instance = type(self)()
            instance.attribute_values = {}
            instance._set_attributes(**values)
            values = instance
        rval = AttributeContainer._container_serialize(values, null_check=null_check)
        self._serialize_undeclared_attributes(values, rval)
        return rval

    def deserialize(self, values):
        instance = self._instantiate(values)
        for attr_name, value in values.items():
            if instance._dynamo_to_python_attr(attr_name) not in instance.get_attributes():
                attr_type, attr_value = next(iter(value.items()))
                instance[attr_name] = DESERIALIZE_CLASS_MAP[attr_type].deserialize(attr_value)
        return instance

    @classmethod
    def is_raw(cls):
        return True

def _get_class_for_serialize(value: Any) -> Attribute:
    if value is None:
        return NullAttribute()
    if isinstance(value, MapAttribute):
        return value
    if isinstance(value, set):
        set_types = {type(v) for v in value}
        if not set_types:
            raise ValueError("Cannot serialize empty set")
        if set_types == {str}:
            return UnicodeSetAttribute()
        if set_types <= {int, float}:
            return NumberSetAttribute()
        if set_types == {bytes}:
            return BinarySetAttribute(legacy_encoding=False)
        raise ValueError(f"Cannot serialize set consisting of types: {', '.join(sorted(map(repr, set_types)))}")
    value_type = type(value)
    attr = SERIALIZE_CLASS_MAP.get(value_type)
    if attr is None:
        raise ValueError(f"Unsupported value type '{value_type}'")
    return attr

class ListAttribute(Generic[_T], Attribute[List[_T]]):
    attr_type = LIST
    element_type: Optional[Type[Attribute]] = None

    def __init__(
        self,
        hash_key: bool = False,
        range_key: bool = False,
        null: Optional[bool] = None,
        default: Optional[Union[Any, Callable[..., Any]]] = None,
        attr_name: Optional[str] = None,
        of: Optional[Type[_T]] = None,
    ) -> None:
        super().__init__(
            hash_key=hash_key,
            range_key=range_key,
            null=null,
            default=default,
            attr_name=attr_name,
        )
        if of:
            if not issubclass(of, Attribute):
                raise ValueError("'of' must be a subclass of Attribute")
            self.element_type = of

    def serialize(self, values, *, null_check: bool = True):
        rval = []
        for idx, value in enumerate(values):
            attr = self._get_serialize_class(value)
            if self.element_type and value is not None and not isinstance(attr, self.element_type):
                raise ValueError("List elements must be of type: {}".format(self.element_type.__name__))
            attr_type = attr.attr_type
            try:
                if isinstance(attr, (ListAttribute, MapAttribute)):
                    attr_value = attr.serialize(value, null_check=null_check)
                else:
                    attr_value = attr.serialize(value)
            except AttributeNullError as e:
                e.prepend_path(f'[{idx}]')
                raise
            if attr_value is None:
                attr_type = NULL
                attr_value = True
            rval.append({attr_type: attr_value})
        return rval

    def deserialize(self, values):
        if self.element_type:
            element_attr: Attribute
            if issubclass(self.element_type, (BinaryAttribute, BinarySetAttribute)):
                element_attr = self.element_type(legacy_encoding=False)
            else:
                element_attr = self.element_type()
                if isinstance(element_attr, MapAttribute):
                    element_attr._make_attribute()
            deserialized_lst = []
            for idx, attribute_value in enumerate(values):
                value = None
                if NULL not in attribute_value:
                    element_attr.attr_name = f'{self.attr_name}[{idx}]' if self.attr_name else f'[{idx}]'
                    value = element_attr.deserialize(element_attr.get_value(attribute_value))
                deserialized_lst.append(value)
            return deserialized_lst
        return [
            DESERIALIZE_CLASS_MAP[attr_type].deserialize(attr_value)
            for v in values for attr_type, attr_value in v.items()
        ]

    def __getitem__(self, idx: int) -> Path:
        if not isinstance(idx, int):
            raise TypeError("list indices must be integers, not {}".format(type(idx).__name__))
        if self.element_type:
            element_attr = self.element_type()
            if isinstance(element_attr, MapAttribute):
                element_attr._make_attribute()
            element_attr.attr_path = list(self.attr_path)
            element_attr.attr_name = '{}[{}]'.format(element_attr.attr_name, idx)
            if isinstance(element_attr, MapAttribute):
                for path_segment in reversed(element_attr.attr_path):
                    element_attr._update_attribute_paths(path_segment)
            return element_attr
        return super().__getitem__(idx)

    def _get_serialize_class(self, value):
        if value is None:
            return NullAttribute()
        if isinstance(value, Attribute):
            return value
        if self.element_type:
            if issubclass(self.element_type, (BinaryAttribute, BinarySetAttribute)):
                return self.element_type(legacy_encoding=False)
            return self.element_type()
        return _get_class_for_serialize(value)

DESERIALIZE_CLASS_MAP: Dict[str, Attribute] = {
    BINARY: BinaryAttribute(legacy_encoding=False),
    BINARY_SET: BinarySetAttribute(legacy_encoding=False),
    BOOLEAN: BooleanAttribute(),
    LIST: ListAttribute(),
    MAP: MapAttribute(),
    NULL: NullAttribute(),
    NUMBER: NumberAttribute(),
    NUMBER_SET: NumberSetAttribute(),
    STRING: UnicodeAttribute(),
    STRING_SET: UnicodeSetAttribute()
}

SERIALIZE_CLASS_MAP: Mapping[type, Attribute] = {
    dict: MapAttribute(),
    list: ListAttribute(),
    bool: BooleanAttribute(),
    float: NumberAttribute(),
    int: NumberAttribute(),
    str: UnicodeAttribute(),
    bytes: BinaryAttribute(legacy_encoding=False),
}