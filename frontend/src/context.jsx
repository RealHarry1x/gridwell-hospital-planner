import { createContext, useContext } from 'react';
export const Workspace = createContext(null);
export const useWorkspace = () => useContext(Workspace);
