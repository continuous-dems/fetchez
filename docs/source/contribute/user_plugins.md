# 🐄 Developing User Plugins (Data Modules)

One of the most powerful features of `fetchez` is its plugin architecture. You can write your own modules to fetch data from custom sources and use them immediately with the full power of the `fetchez` CLI (smart regions, threading, retries, etc.).

## How it Works
1.  `fetchez` scans `~/.fetchez/plugins/` at runtime.
2.  It loads any `.py` file it finds.
3.  It registers any class that inherits from `fetchez.core.FetchModule`.

## Example Plugin
Create a file named `~/.fetchez/plugins/usgs_checkpoints.py`:

```python
from fetchez import core, cli

checkpoints_base_url = 'https://www.sciencebase.gov/catalog/file/get/'
checkpoints_link = '67075e6bd34e969edc59c3e7?f=__disk__80%2F12%2F9e%2F80129e86d18461ed921b288f13e08c62e8590ffb'

@cli.cli_opts(help_text="USGS Elevation Checkpoints")
class CheckPoints3DEP(core.FetchModule):
    def __init__(self, **kwargs):
    	# `name` here becomes the name of fetchez module in the cli
        super().__init__(name='my_checkpoints', **kwargs)

    def run(self):
        # Use self.region if spatial filtering is needed
        if self.region:
             print(f"Searching in region: {self.region}"

    	# This is where you'd normally hit an API, or parse some
        # data, etc.

        self.add_entry_to_results(
            url=f'{checkpoints_url}{checkpoints_link}',
            dst_fn='USGS_CheckPoints.zip',
            data_type='checkpoints',
        )
```

## Testing Your Plugin
Once you save the file, simply run:

```bash

# Check if it loaded
fetchez --modules | grep my_checkpoints

# or
fetchez --search plugin

# Run it
fetchez my_checkpoints
```