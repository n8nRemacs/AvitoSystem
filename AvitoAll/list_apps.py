import frida

device = frida.get_usb_device(timeout=5)
print(f"Device: {device.name}\n")

print("Running applications:")
for app in device.enumerate_applications():
    if app.pid > 0:
        print(f"  {app.pid}: {app.identifier} ({app.name})")
