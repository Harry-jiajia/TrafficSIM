"""Compatibility import for the superseded Leaflet widget name."""

from ui.widgets.maplibre_deck_map import MapLibreDeckMapWidget

LeafletMapWidget = MapLibreDeckMapWidget

__all__ = ["LeafletMapWidget"]
