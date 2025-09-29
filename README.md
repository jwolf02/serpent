# Serpent
Serial Command Prompt

## Usage
Serpent simulates a command promp over a serial interface. It allows to interactively input
command which are sent to the device while simultaneously monitor the devices output.
  
### Example
Start serpent in text mode over serial device ```/dev/cu.usbserial-0001``` with 230400 baud splitting lines on ```\n``` as a delimiter:
```bash
serpent -p /dev/cu.usbserial-0001 -b 230400 --binary
```

## Plugins
By default the serial input is printed out unformatted while user input is sent over the serial as ASCII characters.
In order to change this behaviour the user can register a plugin through with both input and output is routed before being printed on ```STDOUT```.

```Python
def serpent_input_filter(data: bytes, extra_args: dict) -> tuple[list[str], bytes]:
    """
    Parse the input segments from data and return them as a list of strings.
    The remaining bytes that do not form full log lines are returned to be
    passed to the filter again when more input has been read.
    """

    return lines, data

def serpent_output_filter(user_input: str, extra_args: dict) -> bytes:
    """
    Convert a lines of user_input (no '\n' at the end) into a byte sequence
    that is sent over the serial connection.
    """

    return input_as_bytes
```
