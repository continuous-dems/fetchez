# 🐄 Plugins & Extensions (Bring Your Own Code)

Need to fetch data from a specialized local server? Or maybe run a custom script immediately after every download? You don't need to fork the repo!

Fetchez is designed to be extendable in two ways:

* **Data Modules (~/.fetchez/plugins/):** Add new data sources or APIs.

* **Processing Hooks (~/.fetchez/hooks/):** Add new pre, file, or post-processing steps.

Drop your Python scripts into these configuration folders, and they will be automatically registered as native commands.