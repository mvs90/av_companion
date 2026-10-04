# Changelog

## 1.1.0

- Expose the optional LG Dashboard source in the combined AV media player's source list, including unique naming when an input/app uses the same label.
- Route selection through the LG public API after the usual display/supply wake checks, without waking a linked television player. Linked app selection explicitly leaves Dashboard even with a matching cached HDMI input.
- Follow Dashboard selection made directly on the LG entity and preserve automatic standby protection. Requires LG 2.7.0 for Dashboard; older LG API v1 installations retain their existing behavior.

## 1.0.0

Initial independent AV extension for LG Professional Display 2.0/API v1. Optional player, remote, sound system, socket and power-sensor links; combined TV/HomeKit routing; staged standby confirmation; temporary content, announcements and native LG delegation. Includes presentation ownership, guarded socket cuts, entity rename handling and isolated Docker acceptance tests. No migration required.
