## VPinFE Release Notes

### Summary
This is the offical release of vpinfe v2.4.1

### What's New
None

### Fixes
- There is a race condition that causes a heap corruption in glibc when multiple callers get monitor specs in the screeninfo python module.  For whatever reason when multiple requests like this occor at the same time or very close this condition happens.  If someone has multiple monitors its more likely occor because of how vpinfe starts multiple screen setups.  Thanks to @Smitty2k1 for reporting!

### Notes
