"""Windows Service wrapper for astromeshd."""

import sys

if sys.platform == "win32":
    try:
        import servicemanager
        import win32event
        import win32service
        import win32serviceutil

        class AstromeshService(win32serviceutil.ServiceFramework):
            _svc_name_ = "astromeshd"
            _svc_display_name_ = "Astromesh Agent Runtime Daemon"
            _svc_description_ = "Runs the Astromesh AI agent runtime as a Windows service"

            def __init__(self, args):
                win32serviceutil.ServiceFramework.__init__(self, args)
                self.stop_event = win32event.CreateEvent(None, 0, 0, None)

            def SvcStop(self):
                self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
                win32event.SetEvent(self.stop_event)

            def SvcDoRun(self):
                from astromesh_node.daemon.core import main
                main()

        if __name__ == "__main__":
            win32serviceutil.HandleCommandLine(AstromeshService)

    except ImportError:
        print("pywin32 is required for Windows Service support", file=sys.stderr)
        sys.exit(1)
