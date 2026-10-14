/* סל משווה — Service Worker
 * מטרה אחת: כשאין אינטרנט, להציג עמוד "אין חיבור" ידידותי (עם הרשימה השמורה) במקום שגיאה של הדפדפן.
 * לא שומרים מחירים במטמון — הם חייבים להיות עדכניים.
 */
const CACHE = 'sal-mashve-v1';
// הנתיבים יחסית לשורש הדומיין — עובד גם כשהקובץ מוגש מ-/sw.js וגם מ-/app/static/sw.js
const BASE = self.location.origin;
const SHELL = [
  '/app/static/offline.html',
  '/app/static/icon-192.png',
  '/app/static/icon-512.png',
].map(p => BASE + p);

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  // רק ניווט לעמוד (לא WebSocket, לא בקשות נתונים)
  if (req.mode !== 'navigate') return;
  e.respondWith(
    fetch(req).catch(() => caches.match(BASE + '/app/static/offline.html'))
  );
});
