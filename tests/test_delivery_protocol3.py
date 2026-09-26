"""The public delivery must include inherited animation, not only new cues."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from scripts.work_model_delivery import prepare_release, publish_release, verify_release
from tests import test_work_model_delivery as fixture_module
from tests.test_work_model_delivery import sha256


class DeliveryClosureTests(unittest.TestCase):
    setUp = fixture_module.WorkModelDeliveryTests.setUp

    def fixture(self, directory):
        root, afterforge, manifest = fixture_module.WorkModelDeliveryTests().make_inputs(directory)
        legacy = afterforge / 'old-version'
        legacy.mkdir()
        package = afterforge / 'old.fcpxmld'
        package.mkdir()
        movie = package / 'AF__old.mov'
        movie.write_bytes(b'older registered animation')
        (legacy / 'animation-manifest.json').write_text(json.dumps({
            'schemaVersion': '2.0', 'cues': [{'id': 'old', 'deliveryAsset': {
                'fileName': movie.name, 'sha256': sha256(movie),
                'width': 1920, 'height': 1080, 'frameRate': '24',
                'duration': '1s', 'codec': 'prores_4444', 'hasAlpha': True,
            }}],
        }))
        source = root / 'source.fcpxml'
        text = source.read_text().replace('</resources>',
            '<asset id="old" name="AF__old.mov" start="0s" duration="1s" hasVideo="1" format="r1">'
            f'<media-rep kind="original-media" src="{movie.as_uri()}"><bookmark>old-location</bookmark></media-rep>'
            '</asset></resources>').replace(
            '<gap name="base" offset="0s" start="0s" duration="4s"/>',
            '<gap name="base" offset="0s" start="0s" duration="4s">'
            '<asset-clip ref="old" name="AF__old" lane="1" offset="0s" start="0s" duration="1s"/>'
            '</gap>')
        source.write_text(text)
        manifest['sourceHashes']['fcpxml'] = sha256(source)
        return root, afterforge, manifest, movie

    def test_current_delivery_includes_inherited_movie_as_visible_hardlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root, afterforge, manifest, old = self.fixture(directory)
            prepared = prepare_release(root, manifest, afterforge_root=afterforge,
                                       release_id='d0001', input_key='input', dependency_paths=[])
            staged = Path(prepared['stagingPackage'])
            self.assertTrue((staged / old.name).is_file(), 'inherited animation is missing from delivery')
            self.assertEqual((staged / old.name).stat().st_ino, old.stat().st_ino)
            self.assertEqual(prepared['packagePath'], '交付/Episode-One-D0001')
            xml = ET.parse(staged / 'Episode-One-D0001.fcpxml').getroot()
            inherited = xml.find("resources/asset[@id='old']/media-rep")
            self.assertEqual(inherited.get('src'), './AF__old.mov')
            self.assertIsNone(inherited.find('bookmark'))

    def test_duplicate_physical_formal_media_blocks_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root, afterforge, manifest, old = self.fixture(directory)
            prepared = prepare_release(root, manifest, afterforge_root=afterforge,
                                       release_id='d0001', input_key='input', dependency_paths=[])
            (afterforge / 'duplicate.mov').write_bytes(old.read_bytes())
            with self.assertRaisesRegex(ValueError, 'duplicate|重复'):
                publish_release(root, prepared)
            self.assertFalse((afterforge / prepared['packagePath']).exists())

class ProtocolFailureTests(DeliveryClosureTests):
    def prepare(self, root, afterforge, manifest):
        return prepare_release(root, manifest, afterforge_root=afterforge, release_id='d0001', input_key='input', dependency_paths=[])

    def test_nested_repeated_inherited_resource_is_delivered_once(self):
        with tempfile.TemporaryDirectory() as d:
            root, af, manifest, old = self.fixture(d)
            source = root/'source.fcpxml'
            doc = ET.parse(source)
            resources = doc.getroot().find('resources')
            media = ET.SubElement(resources, 'media', {'id':'compound', 'name':'nested'})
            sequence = ET.SubElement(media, 'sequence', {'duration':'2s','format':'r1'})
            spine = ET.SubElement(sequence, 'spine')
            for offset in ('0s','1s'):
                ET.SubElement(spine, 'asset-clip', {'ref':'old','offset':offset,'start':'0s','duration':'1s'})
            gap = doc.getroot().find('.//project/sequence/spine/gap')
            gap.remove(gap[0])
            ET.SubElement(gap, 'ref-clip', {'ref':'compound','lane':'1','offset':'0s','duration':'2s'})
            doc.write(source)
            manifest['sourceHashes']['fcpxml'] = sha256(source)
            prepared = self.prepare(root,af,manifest)
            self.assertEqual(len(prepared['record']['media']), 2)
            self.assertTrue(verify_release(root, af, publish_release(root,prepared)))

    def test_registered_hash_is_recognized_without_afterforge_filename(self):
        with tempfile.TemporaryDirectory() as d:
            root,af,m,old = self.fixture(d)
            renamed = old.with_name('renamed.mov'); old.rename(renamed)
            source=root/'source.fcpxml'
            source.write_text(source.read_text().replace('AF__old.mov','renamed.mov'))
            m['sourceHashes']['fcpxml']=sha256(source)
            prepared=self.prepare(root,af,m)
            self.assertEqual({a['fileName'] for a in prepared['record']['media']},{'AF__cue.mov','renamed.mov'})

    def test_same_name_different_bytes_remain_separate(self):
        with tempfile.TemporaryDirectory() as d:
            root,af,m,old=self.fixture(d)
            m['cues'][0]['deliveryAsset']['fileName']=old.name
            prepared=self.prepare(root,af,m)
            self.assertEqual(len({a['fileName'] for a in prepared['record']['media']}),2)
            publish_release(root,prepared)

    def test_same_movie_used_by_two_new_cues_has_one_file_and_resource(self):
        import copy
        with tempfile.TemporaryDirectory() as d:
            root,af,m,old=self.fixture(d)
            cue=copy.deepcopy(m['cues'][0]);cue['id']='second';cue['layer']=5
            m['cues'].append(cue)
            prepared=self.prepare(root,af,m)
            self.assertEqual(len(prepared['record']['media']),2)
            publish_release(root,prepared)

    def test_old_location_or_bookmark_cannot_be_hidden_in_complete_directory(self):
        from scripts.validate_fcpxml_package import validate_delivery_package
        for kind in ('absolute','bookmark','proxy','marker'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                root,af,m,old=self.fixture(d)
                p=self.prepare(root,af,m);stage=Path(p['stagingPackage']);xml=stage/p['record']['xmlFileName']
                doc=ET.parse(xml);asset=doc.getroot().find("resources/asset[@id='old']");rep=asset.find('media-rep')
                if kind=='absolute': rep.set('src',old.as_uri())
                if kind=='bookmark': ET.SubElement(rep,'bookmark').text='old-path'
                if kind=='proxy': ET.SubElement(asset,'media-rep',{'kind':'proxy-media','src':old.as_uri()})
                if kind=='marker': asset.find('metadata/md').set('value','0'*64)
                doc.write(xml)
                with self.assertRaises(ValueError):validate_delivery_package(stage,root/'source.fcpxml',p['manifest'])
                with self.assertRaises(ValueError):publish_release(root,p)
                self.assertFalse((af/p['packagePath']).exists())

    def test_missing_or_extra_movie_subdirectory_and_symlink_are_rejected(self):
        from scripts.validate_fcpxml_package import validate_delivery_package
        for kind in ('missing','extra','subdir','symlink'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                root,af,m,old=self.fixture(d);p=self.prepare(root,af,m);stage=Path(p['stagingPackage'])
                if kind=='missing': (stage/old.name).unlink()
                if kind=='extra': (stage/'extra.mov').write_bytes(b'extra')
                if kind=='subdir':
                    (stage/'media').mkdir();(stage/old.name).rename(stage/'media'/old.name)
                if kind=='symlink':
                    (stage/old.name).unlink();(stage/old.name).symlink_to(old)
                with self.assertRaises(ValueError):validate_delivery_package(stage,root/'source.fcpxml',p['manifest'])

    def test_verification_is_independent_of_old_package_and_project_assets(self):
        import shutil
        with tempfile.TemporaryDirectory() as d:
            root,af,m,old=self.fixture(d);p=self.prepare(root,af,m);record=publish_release(root,p)
            shutil.rmtree(old.parent)
            shutil.rmtree(af/'old-version')
            shutil.rmtree(root/'fonts')
            (root/'renders/cue.mov').unlink()
            self.assertTrue(verify_release(root,af,record))

    def test_link_and_missing_validator_failures_cannot_fall_back_to_copy(self):
        from unittest.mock import patch
        cases=[('scripts.work_model_delivery.os.link',OSError('link unavailable')),
               ('scripts.delivery_validation.probe_formal_movie',OSError('ffprobe unavailable'))]
        for target,error in cases:
            with self.subTest(target=target),tempfile.TemporaryDirectory() as d:
                root,af,m,old=self.fixture(d)
                with patch(target,side_effect=error),self.assertRaises((ValueError,OSError)):
                    self.prepare(root,af,m)
                self.assertFalse((af/'交付/Episode-One-D0001').exists())
                self.assertFalse(list((root/'releases/.partial').iterdir()))
        with tempfile.TemporaryDirectory() as d:
            root,af,m,old=self.fixture(d)
            with patch('scripts.work_model_delivery._known_dtd',return_value=None),self.assertRaisesRegex(ValueError,'DTD'):
                self.prepare(root,af,m)

    def test_source_changed_between_prepare_and_publish_blocks_release(self):
        with tempfile.TemporaryDirectory() as d:
            root,af,m,old=self.fixture(d);p=self.prepare(root,af,m)
            old.write_bytes(b'changed inherited file')
            with self.assertRaises(ValueError):publish_release(root,p)
            self.assertFalse((af/p['packagePath']).exists())

    def test_unknown_afterforge_media_is_not_treated_as_non_animation(self):
        with tempfile.TemporaryDirectory() as d:
            root,af,m,old=self.fixture(d)
            (af/'old-version/animation-manifest.json').unlink()
            with self.assertRaisesRegex(ValueError,'unverified'):self.prepare(root,af,m)

    def test_legacy_publisher_is_not_a_production_escape_hatch(self):
        from scripts.build_delivery_package import build_delivery_package
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'read-only'):build_delivery_package(Path(d))
            self.assertFalse(list(Path(d).iterdir()))

class DeliveryContractTests(unittest.TestCase):
    def test_runtime_schema_and_readme_share_the_current_contract(self):
        from scripts.delivery_contract import PROTOCOL_VERSION, documentation_block
        root=Path(__file__).resolve().parents[1]
        self.assertIn(documentation_block(), (root/'README.md').read_text())
        schema=json.loads((root/'references/animation-manifest.schema.json').read_text())
        versions={item['properties']['protocolVersion']['const'] for item in schema['properties']['deliveries']['items']['oneOf']}
        self.assertIn(PROTOCOL_VERSION, versions)
        self.assertEqual(PROTOCOL_VERSION, '3')

class SourceReferenceTests(unittest.TestCase):
    def test_local_text_style_refs_are_not_missing_media(self):
        from scripts.delivery_media import reachable_assets
        xml=ET.fromstring('<fcpxml><resources><asset id="a"/></resources><project><clip ref="a"><text><text-style ref="ts22">字幕</text-style></text><text-style-def id="ts22"><text-style font="PingFang SC"/></text-style-def></clip></project></fcpxml>')
        self.assertEqual(set(reachable_assets(xml)),{'a'})

class SourceIdentificationCostTests(DeliveryClosureTests):
    def test_unrelated_large_source_movie_is_not_rehashed_as_animation(self):
        from unittest.mock import patch
        from scripts.delivery_media import collect_inherited
        from scripts.work_model_store import sha
        with tempfile.TemporaryDirectory() as d:
            root,af,m,old=self.fixture(d)
            film=root/'feature.mov';film.write_bytes(b'unrelated feature'*100)
            source=root/'source.fcpxml';doc=ET.parse(source)
            a=ET.SubElement(doc.getroot().find('resources'),'asset',{'id':'feature','name':'feature'})
            ET.SubElement(a,'media-rep',{'kind':'original-media','src':film.as_uri()})
            ET.SubElement(doc.getroot().find('.//project/sequence/spine/gap'),'asset-clip',{'ref':'feature'})
            doc.write(source)
            def checked(path):
                self.assertNotEqual(Path(path),film,'full feature cannot be a matching animation by file size')
                return sha(path)
            with patch('scripts.delivery_media.sha',side_effect=checked):
                bindings=collect_inherited(af,source,m)
            self.assertEqual([b['resourceId'] for b in bindings if b['afterforge']],['old'])

class InheritedRoundtripTests(DeliveryClosureTests):
    def test_roundtrip_covers_inherited_bytes_and_resource_timing(self):
        from scripts.compare_fcpxml_roundtrip import compare_roundtrip
        with tempfile.TemporaryDirectory() as d:
            root,af,m,old=self.fixture(d)
            prepared=prepare_release(root,m,afterforge_root=af,release_id='d0001',input_key='input',dependency_paths=[])
            stage=Path(prepared['stagingPackage']);source=stage/prepared['record']['xmlFileName'];export=stage/'roundtrip.xml'
            export.write_bytes(source.read_bytes())
            result=compare_roundtrip(source,export,prepared['manifest'])
            self.assertEqual(len(result['formalMediaSha256']),2)
            doc=ET.parse(export);doc.getroot().find("resources/asset[@id='old']").set('start','1s');doc.write(export)
            with self.assertRaisesRegex(ValueError,'timing/format'):compare_roundtrip(source,export,prepared['manifest'])
            export.write_bytes(source.read_bytes());(stage/old.name).unlink()
            with self.assertRaisesRegex(ValueError,'media missing|every formal'):compare_roundtrip(source,export,prepared['manifest'])

class WorkspaceUniquenessTests(DeliveryClosureTests):
    def test_unrelated_registered_legacy_duplicates_also_block_global_invariant(self):
        with tempfile.TemporaryDirectory() as d:
            root,af,m,old=self.fixture(d)
            other=af/'old.fcpxmld/AF__unrelated.mov';other.write_bytes(b'another old formal animation')
            (af/'hidden-copy.bin').write_bytes(other.read_bytes())
            registry=af/'old-version/animation-manifest.json';data=json.loads(registry.read_text())
            data['cues'].append({'id':'other','deliveryAsset':{'fileName':other.name,'sha256':sha256(other)}})
            registry.write_text(json.dumps(data))
            prepared=prepare_release(root,m,afterforge_root=af,release_id='d0001',input_key='input',dependency_paths=[])
            with self.assertRaisesRegex(ValueError,'duplicate'):publish_release(root,prepared)
            self.assertFalse((af/prepared['packagePath']).exists())


if __name__ == '__main__':
    unittest.main()
