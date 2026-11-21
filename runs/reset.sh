#!/bin/bash
curl -s -X POST -H "X-Admin-Token: $(cat /Users/harsh223/Desktop/gdg/runs/.admin_token)" http://127.0.0.1:${1:-8080}/admin/reset -o /dev/null -w "reset %{http_code}\n"
