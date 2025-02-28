"""Test Hue migration logic."""
from unittest.mock import patch

from homeassistant.components import hue
from homeassistant.helpers import device_registry as dr, entity_registry as er

from tests.common import MockConfigEntry


async def test_migrate_api_key(hass):
    """Test if username gets migrated to api_key."""
    config_entry = MockConfigEntry(
        domain=hue.DOMAIN,
        data={"host": "0.0.0.0", "api_version": 2, "username": "abcdefgh"},
    )
    await hue.migration.check_migration(hass, config_entry)
    # the username property should have been migrated to api_key
    assert config_entry.data == {
        "host": "0.0.0.0",
        "api_version": 2,
        "api_key": "abcdefgh",
    }


async def test_auto_switchover(hass):
    """Test if config entry from v1 automatically switches to v2."""
    config_entry = MockConfigEntry(
        domain=hue.DOMAIN,
        data={"host": "0.0.0.0", "api_version": 1, "username": "abcdefgh"},
    )

    with patch.object(hue.migration, "is_v2_bridge", retun_value=True), patch.object(
        hue.migration, "handle_v2_migration"
    ) as mock_mig:
        await hue.migration.check_migration(hass, config_entry)
        assert len(mock_mig.mock_calls) == 1
        # the api version should now be version 2
        assert config_entry.data == {
            "host": "0.0.0.0",
            "api_version": 2,
            "api_key": "abcdefgh",
        }


async def test_light_entity_migration(
    hass, mock_bridge_v2, mock_config_entry_v2, v2_resources_test_data
):
    """Test if entity schema for lights migrates from v1 to v2."""
    config_entry = mock_bridge_v2.config_entry = mock_config_entry_v2

    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    # create device/entity with V1 schema in registry
    device = dev_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(hue.DOMAIN, "00:17:88:01:09:aa:bb:65")},
    )
    ent_reg.async_get_or_create(
        "light",
        hue.DOMAIN,
        "00:17:88:01:09:aa:bb:65",
        suggested_object_id="migrated_light_1",
        device_id=device.id,
    )

    # now run the migration and check results
    await mock_bridge_v2.api.load_test_data(v2_resources_test_data)
    await hass.async_block_till_done()

    with patch(
        "homeassistant.components.hue.migration.HueBridgeV2",
        return_value=mock_bridge_v2.api,
    ):
        await hue.migration.handle_v2_migration(hass, config_entry)

    # migrated device should have new identifier (guid) and old style (mac)
    migrated_device = dev_reg.async_get(device.id)
    assert migrated_device is not None
    assert migrated_device.identifiers == {
        (hue.DOMAIN, "0b216218-d811-4c95-8c55-bbcda50f9d50"),
        (hue.DOMAIN, "00:17:88:01:09:aa:bb:65"),
    }
    # the entity should have the new identifier (guid)
    migrated_entity = ent_reg.async_get("light.migrated_light_1")
    assert migrated_entity is not None
    assert migrated_entity.unique_id == "02cba059-9c2c-4d45-97e4-4f79b1bfbaa1"


async def test_sensor_entity_migration(
    hass, mock_bridge_v2, mock_config_entry_v2, v2_resources_test_data
):
    """Test if entity schema for sensors migrates from v1 to v2."""
    config_entry = mock_bridge_v2.config_entry = mock_config_entry_v2

    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    # create device with V1 schema in registry for Hue motion sensor
    device_mac = "00:17:aa:bb:cc:09:ac:c3"
    device = dev_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={(hue.DOMAIN, device_mac)}
    )

    # mapping of device_class to new id
    sensor_mappings = {
        ("temperature", "sensor", "66466e14-d2fa-4b96-b2a0-e10de9cd8b8b"),
        ("illuminance", "sensor", "d504e7a4-9a18-4854-90fd-c5b6ac102c40"),
        ("battery", "sensor", "669f609d-4860-4f1c-bc25-7a9cec1c3b6c"),
        ("motion", "binary_sensor", "b6896534-016d-4052-8cb4-ef04454df62c"),
    }

    # create entities with V1 schema in registry for Hue motion sensor
    for dev_class, platform, new_id in sensor_mappings:
        ent_reg.async_get_or_create(
            platform,
            hue.DOMAIN,
            f"{device_mac}-{dev_class}",
            suggested_object_id=f"hue_migrated_{dev_class}_sensor",
            device_id=device.id,
            device_class=dev_class,
        )

    # now run the migration and check results
    await mock_bridge_v2.api.load_test_data(v2_resources_test_data)
    await hass.async_block_till_done()

    with patch(
        "homeassistant.components.hue.migration.HueBridgeV2",
        return_value=mock_bridge_v2.api,
    ):
        await hue.migration.handle_v2_migration(hass, config_entry)

    # migrated device should have new identifier (guid) and old style (mac)
    migrated_device = dev_reg.async_get(device.id)
    assert migrated_device is not None
    assert migrated_device.identifiers == {
        (hue.DOMAIN, "2330b45d-6079-4c6e-bba6-1b68afb1a0d6"),
        (hue.DOMAIN, device_mac),
    }
    # the entities should have the correct V2 identifier (guid)
    for dev_class, platform, new_id in sensor_mappings:
        migrated_entity = ent_reg.async_get(
            f"{platform}.hue_migrated_{dev_class}_sensor"
        )
        assert migrated_entity is not None
        assert migrated_entity.unique_id == new_id


async def test_group_entity_migration(
    hass, mock_bridge_v2, mock_config_entry_v2, v2_resources_test_data
):
    """Test if entity schema for grouped_lights migrates from v1 to v2."""
    config_entry = mock_bridge_v2.config_entry = mock_config_entry_v2

    ent_reg = er.async_get(hass)

    # create (deviceless) entity with V1 schema in registry
    ent_reg.async_get_or_create(
        "light",
        hue.DOMAIN,
        "3",
        suggested_object_id="hue_migrated_grouped_light",
        config_entry=config_entry,
    )

    # now run the migration and check results
    await mock_bridge_v2.api.load_test_data(v2_resources_test_data)
    await hass.async_block_till_done()
    with patch(
        "homeassistant.components.hue.migration.HueBridgeV2",
        return_value=mock_bridge_v2.api,
    ):
        await hue.migration.handle_v2_migration(hass, config_entry)

    # the entity should have the new identifier (guid)
    migrated_entity = ent_reg.async_get("light.hue_migrated_grouped_light")
    assert migrated_entity is not None
    assert migrated_entity.unique_id == "e937f8db-2f0e-49a0-936e-027e60e15b34"
