- [x] Verify that the copilot-instructions.md file in the .github directory is created.
- [x] Clarify Project Requirements
- [x] Scaffold the Project
- [x] Customize the Project
- [ ] Install Required Extensions
- [ ] Compile the Project
- [ ] Create and Run Task
- [ ] Launch the Project
- [ ] Ensure Documentation is Complete

## Progress Summary
- Project type selected: Full-stack attendance management website.
- Tech stack selected: FastAPI + React (Vite) + PostgreSQL.
- Frontend scaffold created in `frontend/`.
- Backend scaffold created in `backend/` with import parser endpoints.
- Root Docker Compose added for PostgreSQL.

## Development Rules
- Use current directory as project root.
- Keep architecture modular by domain (import, employees, timesheets, overrides, export).
- Require override reason for all manual attendance edits.
- Keep import pipeline traceable by upload batch metadata.
