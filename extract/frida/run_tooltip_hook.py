import frida, time, io

out = io.open("tooltip_output.log", "a", encoding="utf-8")

def on_message(message, data):
    if message["type"] == "send":
        out.write("MSG: " + str(message["payload"]) + "\n")
    elif message["type"] == "error":
        out.write("ERR: " + str(message["stack"]) + "\n")
    out.flush()

session = frida.attach(1848)
src = open("combined_tooltip.js", encoding="utf-8").read()
script = session.create_script(src)
script.on("message", on_message)
script.load()
out.write("LOADED\n")
out.flush()

while True:
    time.sleep(1)
