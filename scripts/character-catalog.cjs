/* Offline helpers consume the actual Python character registry, never private config. */
const {execFileSync}=require('node:child_process'),path=require('node:path');
const source="import json; from okabebot.characters import motion_catalog; from okabebot.scene_sets import CATALOG; print(json.dumps(dict(motion=motion_catalog(),scenes=CATALOG)))";
module.exports=JSON.parse(execFileSync(process.env.PYTHON||'python3',['-c',source],{cwd:path.resolve(__dirname,'..'),encoding:'utf8'}));
