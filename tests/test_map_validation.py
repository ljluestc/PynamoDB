import pytest
import unittest

from pynamodb.attributes import MapAttribute, UnicodeAttribute, NumberAttribute, BooleanAttribute
from pynamodb.exceptions import NoneValueException, TypeMismatchError
from pynamodb.models import Model


class TestMapModel(Model):
    class Meta:
        table_name = 'test_map_model'
        host = 'http://localhost:8000'

    id = UnicodeAttribute(hash_key=True)


class TestNestedMap(MapAttribute):
    name = UnicodeAttribute()
    age = NumberAttribute()
    is_active = BooleanAttribute(null=True)


class TestValidationMapModel(Model):
    class Meta:
        table_name = 'test_validation_map_model'
        host = 'http://localhost:8000'

    id = UnicodeAttribute(hash_key=True)
    nested_map = TestNestedMap(required_keys=['name', 'age'])


class MapValidationTestCase(unittest.TestCase):

    def test_map_validation_none_value(self):
        # Test that NoneValueException is raised when required keys are missing
        with self.assertRaises(NoneValueException) as context:
            model = TestValidationMapModel(id='test1', nested_map={'name': 'Test'})
            model.nested_map.is_correctly_typed('nested_map', model.get_attributes()['nested_map'])

        self.assertEqual("Required attribute 'nested_map.age' cannot be None", str(context.exception))

    def test_map_validation_type_mismatch(self):
        # Test that TypeMismatchError is raised when type doesn't match
        with self.assertRaises(TypeMismatchError) as context:
            model = TestValidationMapModel(id='test1', nested_map={'name': 'Test', 'age': 'not_a_number'})
            model.nested_map.is_correctly_typed('nested_map', model.get_attributes()['nested_map'])

        self.assertEqual("Attribute 'nested_map.age' is of type str, expected type NumberAttribute", str(context.exception))

    def test_map_validation_valid(self):
        # Test that validation passes for valid data
        model = TestValidationMapModel(id='test1', nested_map={'name': 'Test', 'age': 25})
        result = model.nested_map.is_correctly_typed('nested_map', model.get_attributes()['nested_map'])
        self.assertTrue(result)

        # Test with optional attribute
        model = TestValidationMapModel(id='test1', nested_map={'name': 'Test', 'age': 25, 'is_active': True})
        result = model.nested_map.is_correctly_typed('nested_map', model.get_attributes()['nested_map'])
        self.assertTrue(result)
from pynamodb.attributes import MapAttribute, UnicodeAttribute, NumberAttribute, BooleanAttribute
from pynamodb.exceptions import AttributeNullError, TypeMismatchError
from pynamodb.models import Model


class TestMapValidation:
    def test_required_key_validation(self):
        class UserMap(MapAttribute):
            name = UnicodeAttribute()
            age = NumberAttribute()

        # Create map with required keys
        user_map = UserMap(required_keys=['name'])

        # Test with missing required key
        with pytest.raises(AttributeNullError) as excinfo:
            user_map.serialize({'age': 25})
        assert "Attribute 'name' cannot be None" in str(excinfo.value)

        # Test with required key present
        serialized = user_map.serialize({'name': 'John', 'age': 25})
        assert 'name' in serialized
        assert 'age' in serialized

        # Test with required key present but None
        with pytest.raises(AttributeNullError) as excinfo:
            user_map.serialize({'name': None, 'age': 25})
        assert "Attribute 'name' cannot be None" in str(excinfo.value)

    def test_type_validation(self):
        class ProfileMap(MapAttribute):
            name = UnicodeAttribute()
            age = NumberAttribute()
            is_active = BooleanAttribute()

        profile = ProfileMap()

        # Test with correct types
        serialized = profile.serialize({
            'name': 'John',
            'age': 30,
            'is_active': True
        })
        assert 'name' in serialized
        assert 'age' in serialized
        assert 'is_active' in serialized

        # Test with incorrect type
        with pytest.raises(TypeMismatchError) as excinfo:
            profile.serialize({
                'name': 'John',
                'age': '30',  # string instead of number
                'is_active': True
            })
        assert "expected type number" in str(excinfo.value).lower()

        # Test with another incorrect type
        with pytest.raises(TypeMismatchError) as excinfo:
            profile.serialize({
                'name': 123,  # number instead of string
                'age': 30,
                'is_active': True
            })
        assert "expected type str" in str(excinfo.value).lower()

    def test_nested_map_validation(self):
        class AddressMap(MapAttribute):
            street = UnicodeAttribute()
            city = UnicodeAttribute()
import unittest

from pynamodb.attributes import MapAttribute, UnicodeAttribute, NumberAttribute, BooleanAttribute
from pynamodb.exceptions import NoneValueException, TypeMismatchError
from pynamodb.models import Model


class TestMapModel(Model):
    class Meta:
        table_name = 'test_map_model'
        host = 'http://localhost:8000'

    id = UnicodeAttribute(hash_key=True)


class TestNestedMap(MapAttribute):
    name = UnicodeAttribute()
    age = NumberAttribute()
    is_active = BooleanAttribute(null=True)


class TestValidationMapModel(Model):
    class Meta:
        table_name = 'test_validation_map_model'
        host = 'http://localhost:8000'

    id = UnicodeAttribute(hash_key=True)
    nested_map = TestNestedMap(required_keys=['name', 'age'])


class MapValidationTestCase(unittest.TestCase):

    def test_map_validation_none_value(self):
        # Test that NoneValueException is raised when required keys are missing
        with self.assertRaises(NoneValueException) as context:
            model = TestValidationMapModel(id='test1', nested_map={'name': 'Test'})
            model.nested_map.is_correctly_typed('nested_map', model.get_attributes()['nested_map'])

        self.assertEqual("Required attribute 'nested_map.age' cannot be None", str(context.exception))

    def test_map_validation_type_mismatch(self):
        # Test that TypeMismatchError is raised when type doesn't match
        with self.assertRaises(TypeMismatchError) as context:
            model = TestValidationMapModel(id='test1', nested_map={'name': 'Test', 'age': 'not_a_number'})
            model.nested_map.is_correctly_typed('nested_map', model.get_attributes()['nested_map'])

        self.assertEqual("Attribute 'nested_map.age' is of type str, expected type NumberAttribute", str(context.exception))

    def test_map_validation_valid(self):
        # Test that validation passes for valid data
        model = TestValidationMapModel(id='test1', nested_map={'name': 'Test', 'age': 25})
        result = model.nested_map.is_correctly_typed('nested_map', model.get_attributes()['nested_map'])
        self.assertTrue(result)

        # Test with optional attribute
        model = TestValidationMapModel(id='test1', nested_map={'name': 'Test', 'age': 25, 'is_active': True})
        result = model.nested_map.is_correctly_typed('nested_map', model.get_attributes()['nested_map'])
        self.assertTrue(result)
        class UserMap(MapAttribute):
            name = UnicodeAttribute()
            address = AddressMap()

        # Test with nested required key
        address_map = AddressMap(required_keys=['city'])
        user_map = UserMap()
        user_map.address = address_map

        # Should raise exception for missing required nested key
        with pytest.raises(AttributeNullError) as excinfo:
            user_map.serialize({
                'name': 'John',
                'address': {
                    'street': '123 Main St'
                }
            })
        assert "Attribute 'address.city' cannot be None" in str(excinfo.value)

        # Should validate successfully with all required keys
        serialized = user_map.serialize({
            'name': 'John',
            'address': {
                'street': '123 Main St',
                'city': 'New York'
            }
        })
        assert 'name' in serialized
        assert 'address' in serialized

    def test_nested_type_validation(self):
        class AddressMap(MapAttribute):
            street = UnicodeAttribute()
            zip_code = NumberAttribute()

        class UserMap(MapAttribute):
            name = UnicodeAttribute()
            address = AddressMap()

        user_map = UserMap()

        # Should raise exception for incorrect type in nested map
        with pytest.raises(TypeMismatchError) as excinfo:
            user_map.serialize({
                'name': 'John',
                'address': {
                    'street': '123 Main St',
                    'zip_code': '10001'  # string instead of number
                }
            })
        assert "Attribute 'address.zip_code'" in str(excinfo.value)
        assert "expected type number" in str(excinfo.value).lower()
