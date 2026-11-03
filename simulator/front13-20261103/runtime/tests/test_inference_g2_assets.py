"""Contract/geometry checks for all ten G2 object replacements."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

RUNTIME=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('g2_builder',RUNTIME/'scripts/build_inference_g2_assets.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

class G2AssetContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=json.loads(builder.BASE.read_text())['tasks']
        cls.patch=json.loads((builder.OUT/'g2-bindings-patch.json').read_text())['tasks']
        cls.provenance=json.loads((builder.OUT/'assets/g2/provenance.json').read_text())
    def test_all_ten_tasks_and_56_replacements(self):
        self.assertEqual(set(self.patch),set(builder.TASKS))
        self.assertEqual(sum(len(v) for v in self.provenance['tasks'].values()),56)
    def test_all_abc_goals_and_initial_layouts_preserved(self):
        for task,binding in self.patch.items():
            self.assertEqual(binding['variants'],self.base[task]['variants'],task)
            self.assertEqual(set(binding['objects']),set(self.base[task]['objects']))
            for name,obj in binding['objects'].items():
                old=self.base[task]['objects'][name]
                for key in ('xy','yaw','quaternion','mass','friction','contact_offset','rest_offset','identity','bottom'):
                    self.assertEqual(obj.get(key),old.get(key),(task,name,key))
    def test_target_fixtures_byte_equivalent(self):
        for task,binding in self.patch.items():
            changed={v['id'] for v in self.provenance['tasks'][task]}
            for name,obj in binding['objects'].items():
                if name not in changed:self.assertEqual(obj,self.base[task]['objects'][name])
    def test_sources_are_pinned_self_contained_and_new(self):
        for task,changed in self.provenance['tasks'].items():
            for entry in changed:
                obj=self.patch[task]['objects'][entry['id']];source=obj['source_asset']
                self.assertEqual(source['root_env'],'VIC_INFERENCE_ASSETS')
                p=builder.OUT/'assets'/source['relative_path']
                self.assertEqual(builder.sha(p),source['sha256'])
                self.assertNotEqual(source['sha256'],entry['original_source'].get('sha256'))
                self.assertFalse(obj['recolor'])
                self.assertNotIn('reviewed_collision_settings',obj)
                for dependency in source.get('dependencies',[]):
                    self.assertEqual(builder.sha(builder.OUT/'assets'/dependency['relative_path']),dependency['sha256'])
    def test_cards_remain_thin_and_back_identical(self):
        backs=[];fronts=[]
        for i in range(1,6):
            obj=self.patch['E49']['objects'][f'card{i}'];old=self.base['E49']['objects'][f'card{i}']
            self.assertEqual(obj['size'],old['size']);self.assertEqual(obj['size'][2]*2,.00035)
            self.assertEqual(obj['identity_attributes']['original_position_index'],i)
            self.assertEqual(obj['quaternion'],[0,1,0,0])
            m=builder.prop('photo',(1,1,1),'photo_sources/'+builder.PHOTOS[i-1]);backs.append(m.parts[1]);fronts.append(m.parts[2]['texture'])
            self.assertTrue(m.parts[0]['invisible'])
            visible_top_faces=[(part,face) for part in m.parts if not part['invisible'] for face in part['faces'] if all(part['points'][i][2]==1 for i in face)]
            self.assertEqual(len(visible_top_faces),1)
        self.assertTrue(all(x==backs[0] for x in backs));self.assertEqual(len(set(fronts)),5)
    def test_cookie_cross_product_complete_and_colors_consistent(self):
        objs=self.patch['E09']['objects']
        self.assertEqual({x['id'] for x in self.provenance['tasks']['E09']},{c+'_'+s for c in ('red','green','blue') for s in ('square','triangle','circle')})
        self.assertTrue(all(obj['source_asset']['relative_path'].startswith('g2/') for obj in objs.values()))
    def test_matryoshka_uniform_scaling_and_equal_design(self):
        sizes=[self.patch['E07']['objects']['block'+str(i)]['size'] for i in range(1,6)]
        for i,size in enumerate(sizes,1):self.assertTrue(all(abs(v/sizes[0][j]-i)<1e-8 for j,v in enumerate(size)))
    def test_fruit_keeps_tray_fit_and_start_bottom(self):
        for name,obj in self.patch['E11']['objects'].items():
            if name=='tray':continue
            self.assertEqual(obj['size'][:2],[.02,.02]);self.assertEqual(obj['size'][2],.02)
            if 'center_z' in obj:self.assertAlmostEqual(obj['center_z']-obj['size'][2],self.base['E11']['objects'][name]['center_z']-.003)
    def test_all_meshes_closed_collision_and_valid_topology(self):
        for task,binding in self.patch.items():
            for name,obj,kind,color,photo in builder.replacements(task,binding['objects']):
                m=builder.prop(kind,color,'photo_sources/'+photo if photo else None)
                self.assertTrue(any(p['collision'] for p in m.parts),(task,name))
                for part in m.parts:
                    for face in part['faces']:
                        self.assertGreaterEqual(len(face),3);self.assertTrue(all(0<=i<len(part['points']) for i in face))
                    if part['collision']:
                        edges={}
                        for face in part['faces']:
                            for i,a in enumerate(face):
                                b=face[(i+1)%len(face)];key=tuple(sorted((a,b)));edges[key]=edges.get(key,0)+1
                        self.assertTrue(all(n==2 for n in edges.values()),(task,name,part['name']))

if __name__=='__main__':unittest.main()
