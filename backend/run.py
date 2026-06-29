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
        # Exit gracefully with code 0 on Ctrl+C to prevent tracebacks and pnpm errors
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)

if __name__ == "__main__":
    main()
