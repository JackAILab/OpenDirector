// Follow the editor's visible menus; never bypass UI handlers with forced clicks.
const tools=new Set(['editorMediaToggle','settings','editorMixerToggle','assistant','review','themeToggle']);
async function clickEditorControl(page,id){
 const control=page.locator('#'+id);
 if(!await control.isVisible())await page.locator(tools.has(id)?'#editorToolsToggle':'#editorExportMenuToggle').click();
 await control.click();
}
module.exports={clickEditorControl};
