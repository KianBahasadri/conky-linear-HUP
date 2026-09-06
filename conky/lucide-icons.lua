-- Lucide path data, ISC licensed (assets/LUCIDE-LICENSE.txt).
-- Every icon sits on the 24×24 grid and is stroked at 2px with round caps
-- and joins; `<rect rx>` elements are written as equivalent arc paths.
return {
  cpu = {
    'M12 20v2', 'M12 2v2', 'M17 20v2', 'M17 2v2', 'M2 12h2', 'M2 17h2', 'M2 7h2',
    'M20 12h2', 'M20 17h2', 'M20 7h2', 'M7 20v2', 'M7 2v2',
    'M6 4h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z',
    'M9 8h6a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z',
  },
  ['memory-stick'] = {
    'M12 12v-2', 'M12 18v-2', 'M16 12v-2', 'M16 18v-2', 'M2 11h1.5', 'M20 18v-2',
    'M20.5 11H22', 'M4 18v-2', 'M8 12v-2', 'M8 18v-2',
    'M4 6h16a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z',
  },
  download = {'M12 15V3', 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4', 'm7 10 5 5 5-5'},
  upload = {'M12 3v12', 'm17 8-5-5-5 5', 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4'},
  ['laptop-minimal'] = {
    'M5 4h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z',
    'M2 20h20',
  },
  smartphone = {
    'M7 2h10a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z',
    'M12 18h.01',
  },
  monitor = {
    'M4 3h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z',
    'M8 21h8', 'M12 17v4',
  },
  terminal = {'M12 19h8', 'm4 17 6-6-6-6'},
  ['triangle-alert'] = {
    'm21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3z',
    'M12 9v4', 'M12 17h.01',
  },
  eye = {
    'M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0',
    'M15 12a3 3 0 1 1-6 0a3 3 0 1 1 6 0',
  },
  ['eye-closed'] = {
    'm15 18-.722-3.25', 'M2 8a10.645 10.645 0 0 0 20 0',
    'm20 15-1.726-2.05', 'm4 15 1.726-2.05', 'm9 18 .722-3.25',
  },
}
