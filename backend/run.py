import os
import sys
import uvicorn

def main():
    # Insert backend directory to path to resolve main:app correctly
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, backend_dir)
    
    # Check if --reload flag is passed from command line
    reload = "--reload" in sys.argv
    
    try:
        # Run uvicorn server on port 8000
        uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=reload)
    except KeyboardInterrupt:
        # Exit gracefully with code 0 on Ctrl+C
        pass
    finally:
        # If interrupted (Ctrl+C) again during Python's interpreter atexit teardown
        # (e.g. while pymongo is shutting down background threads), exit instantly and cleanly
        import signal
        signal.signal(signal.SIGINT, lambda sig, frame: os._exit(0))
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)

if __name__ == "__main__":
    main()
