import hashlib
import json
from pathlib import Path

import pytest
import yaml

from trafficverse.maps import OpenDriveMapCompiler, load_network, validate_compiled_bundle
from trafficverse.maps.errors import MapCompileError
from trafficverse.maps.validation import route_is_reachable


def _opendrive(geometry: str = "<line/>") -> str:
    return f"""<OpenDRIVE>
  <header revMajor="1" revMinor="4" name="fixture" version="1.0"/>
  <road name="main" length="100" id="1" junction="-1">
    <link><successor elementType="road" elementId="2" contactPoint="start"/></link>
    <planView><geometry s="0" x="0" y="0" hdg="0" length="100">{geometry}</geometry></planView>
    <lanes><laneSection s="0"><right>
      <lane id="-1" type="driving"><link><successor id="-1"/></link>
        <width sOffset="0" a="3.5" b="0" c="0" d="0"/><speed max="13.89"/>
      </lane>
      <lane id="-2" type="driving"><link><successor id="-2"/></link>
        <width sOffset="0" a="3.5" b="0" c="0" d="0"/><speed max="13.89"/>
      </lane>
    </right></laneSection></lanes>
    <signals><signal id="light-1" s="90" t="0" dynamic="yes"/></signals>
  </road>
  <road name="exit" length="100" id="2" junction="-1">
    <link><predecessor elementType="road" elementId="1" contactPoint="end"/></link>
    <planView><geometry s="0" x="100" y="0" hdg="0" length="100"><line/></geometry></planView>
    <lanes><laneSection s="0"><right>
      <lane id="-1" type="driving"><link><predecessor id="-1"/></link>
        <width sOffset="0" a="3.5" b="0" c="0" d="0"/>
      </lane>
      <lane id="-2" type="driving"><link><predecessor id="-2"/></link>
        <width sOffset="0" a="3.5" b="0" c="0" d="0"/>
      </lane>
    </right></laneSection></lanes>
  </road>
</OpenDRIVE>"""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_compiler_freezes_deterministic_network_geojson_and_manifest(tmp_path: Path) -> None:
    source = tmp_path / "Town04.xodr"
    source.write_text(_opendrive(), encoding="utf-8")
    first = tmp_path / "first"
    second = tmp_path / "second"

    result = OpenDriveMapCompiler().compile(source, first, map_id="town04-test")
    OpenDriveMapCompiler().compile(source, second, map_id="town04-test")

    assert _sha256(first / "network.json") == _sha256(second / "network.json")
    assert _sha256(first / "network.geojson") == _sha256(second / "network.geojson")
    assert result.lane_count == 4
    assert result.link_count == 2
    network = load_network(result.network_path)
    assert network.schema_version == "traffic-network/1.0"
    assert len(network.signals) == 1
    routes = yaml.safe_load((first / "routes.yaml").read_text(encoding="utf-8"))["routes"]
    assert len(routes) == 50
    assert all(route_is_reachable(network, tuple(route["lane_ids"])) for route in routes)
    geojson = json.loads(result.geojson_path.read_text(encoding="utf-8"))
    assert len(geojson["features"]) == len(network.lanes) + len(network.signals)
    signal_features = [
        feature for feature in geojson["features"] if feature["geometry"]["type"] == "Point"
    ]
    assert signal_features[0]["properties"]["signal_id"] == network.signals[0].signal_id
    assert validate_compiled_bundle(first) == network


def test_compiler_rejects_unknown_critical_geometry(tmp_path: Path) -> None:
    source = tmp_path / "unsupported.xodr"
    source.write_text(_opendrive("<bezier/>"), encoding="utf-8")

    with pytest.raises(MapCompileError, match="unsupported critical"):
        OpenDriveMapCompiler().compile(source, tmp_path / "out", map_id="invalid")
