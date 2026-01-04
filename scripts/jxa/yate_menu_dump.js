ObjC.import('stdlib');

function dumpMenuItem(mi) {
  const out = { title: (mi.title && mi.title()) ? mi.title() : "" };

  // enabled / shortcut if available
  try { out.enabled = mi.enabled(); } catch (e) {}
  try { out.keyEquivalent = mi.keyEquivalent(); } catch (e) {}
  try { out.keyEquivalentModifierMask = mi.keyEquivalentModifierMask(); } catch (e) {}

  // submenu recursion
  try {
    const hasMenu = mi.menus && mi.menus().length > 0;
    if (hasMenu) {
      const sub = mi.menus()[0];
      const items = sub.menuItems();
      out.items = [];
      for (let i = 0; i < items.length; i++) out.items.push(dumpMenuItem(items[i]));
    }
  } catch (e) {}

  return out;
}

function dumpMenuBar(proc) {
  const mb = proc.menuBars[0];
  const tops = mb.menuBarItems();
  const res = [];
  for (let i = 0; i < tops.length; i++) {
    const t = tops[i];
    const topTitle = t.name();
    const topMenu = t.menus[0];
    const items = topMenu.menuItems();
    const topOut = { menu: topTitle, items: [] };
    for (let j = 0; j < items.length; j++) topOut.items.push(dumpMenuItem(items[j]));
    res.push(topOut);
  }
  return res;
}

const se = Application('System Events');
se.includeStandardAdditions = true;

const proc = se.processes.byName('Yate');
if (!proc.exists()) {
  console.log(JSON.stringify({ error: "Yate is not running" }, null, 2));
  $.exit(1);
}

const payload = dumpMenuBar(proc);
console.log(JSON.stringify(payload, null, 2));
