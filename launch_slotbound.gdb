set pagination off
set confirm off
set print thread-events off
set breakpoint pending on
run
python verify_breakpoint()
stepi 2
python verify_loaded_arguments()
detach
python verify_module_loaded()
