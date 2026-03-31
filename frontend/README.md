# Hierarchy Mapper Frontend

Built with Next.js (App Router) and React Flow for highly customizable network graphs.

## Setup

1. Install dependencies (make sure `reactflow` is also installed):
```bash
npm install
npm install reactflow
```

2. Run the development server:
```bash
npm run dev
```

Open `http://localhost:3000` in your browser.

## Features
- **Network Graph Visualization**: The UI dynamically graphs out hierarchy and supply-chain nodes using `reactflow`.
- **Custom Modules**: The node design is heavily customized using Vanilla CSS modules to provide a rich UI/UX (Glassmorphism, dark theme).
- **Backend Connected**: It connects to `http://localhost:8000/api/v1/hierarchy`.
