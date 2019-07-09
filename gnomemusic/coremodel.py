import math

import gi
gi.require_versions({'Dazzle': '1.0', 'Gfm': '0.1'})
from gi.repository import Dazzle, GObject, Gio, Gfm, Gtk
from gi._gi import pygobject_new_full

from gnomemusic import log
from gnomemusic.coreartist import CoreArtist
from gnomemusic.coregrilo import CoreGrilo
from gnomemusic.coresong import CoreSong
from gnomemusic.grilowrappers.grltrackerplaylists import Playlist
from gnomemusic.player import PlayerPlaylist
from gnomemusic.songliststore import SongListStore
from gnomemusic.widgets.songwidget import SongWidget

# The basic premisis is that an album (CoreAlbum) consist of a
# number of discs (CoreDisc) which contain a number of songs
# (CoreSong). All discs are a filtered Gio.Listmodel of all the songs
# available in the master Gio.ListModel.
#
# CoreAlbum and CoreDisc contain a Gio.ListModel of the child
# object.
#
# CoreAlbum(s) => CoreDisc(s) => CoreSong(s)
#
# For the playlist model, the CoreArtist or CoreAlbum derived discs are
# flattened and recreated as a new model. This is to allow for multiple
# occurences of the same song: same grilo id, but unique object.


class CoreModel(GObject.GObject):

    __gsignals__ = {
        "playlist-loaded": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "playlists-loaded": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    @log
    def __init__(self, coreselection):
        super().__init__()

        self._flatten_model = None
        self._search_signal_id = None
        self._song_signal_id = None

        self._model = Gio.ListStore.new(CoreSong)
        self._songliststore = SongListStore(self._model)

        self._coreselection = coreselection
        self._album_model = Gio.ListStore()
        self._album_model_sort = Gfm.SortListModel.new(self._album_model)
        self._album_model_sort.set_sort_func(
            self._wrap_list_store_sort_func(self._albums_sort))

        self._artist_model = Gio.ListStore.new(CoreArtist)
        self._artist_model_sort = Gfm.SortListModel.new(self._artist_model)
        self._artist_model_sort.set_sort_func(
            self._wrap_list_store_sort_func(self._artist_sort))

        self._playlist_model = Gio.ListStore.new(CoreSong)
        self._playlist_model_sort = Gfm.SortListModel.new(self._playlist_model)

        self._song_search_proxy = Gio.ListStore.new(Gfm.FilterListModel)
        self._song_search_flatten = Gfm.FlattenListModel.new(CoreSong)
        self._song_search_flatten.set_model(self._song_search_proxy)

        self._album_search_model = Dazzle.ListModelFilter.new(
            self._album_model)
        self._album_search_model.set_filter_func(lambda a: False)

        self._artist_search_model = Dazzle.ListModelFilter.new(
            self._artist_model)
        self._artist_search_model.set_filter_func(lambda a: False)

        self._playlists_model = Gio.ListStore.new(Playlist)
        self._playlists_model_filter = Dazzle.ListModelFilter.new(
            self._playlists_model)
        self._playlists_model_sort = Gfm.SortListModel.new(
            self._playlists_model_filter)
        self._playlists_model_sort.set_sort_func(
            self._wrap_list_store_sort_func(self._playlists_sort))

        self._grilo = CoreGrilo(self, self._coreselection)

    def _filter_selected(self, coresong):
        return coresong.props.selected

    def _albums_sort(self, album_a, album_b):
        return album_b.props.title.casefold() < album_a.props.title.casefold()

    def _artist_sort(self, artist_a, artist_b):
        name_a = artist_a.props.artist.casefold()
        name_b = artist_b.props.artist.casefold()
        return name_a > name_b

    def _playlists_sort(self, playlist_a, playlist_b):
        if playlist_a.props.is_smart:
            if not playlist_b.props.is_smart:
                return -1
            title_a = playlist_a.props.title.casefold()
            title_b = playlist_b.props.title.casefold()
            return title_a > title_b

        if playlist_b.props.is_smart:
            return 1

        # cannot use GLib.DateTime.compare
        # https://gitlab.gnome.org/GNOME/pygobject/issues/334
        # newest first
        date_diff = playlist_b.props.creation_date.difference(
            playlist_a.props.creation_date)
        return math.copysign(1, date_diff)

    def _wrap_list_store_sort_func(self, func):

        def wrap(a, b, *user_data):
            a = pygobject_new_full(a, False)
            b = pygobject_new_full(b, False)
            return func(a, b, *user_data)

        return wrap

    @log
    def get_album_model(self, media):
        disc_model = Gio.ListStore()
        disc_model_sort = Gfm.SortListModel.new(disc_model)

        def _disc_order_sort(disc_a, disc_b):
            return disc_a.props.disc_nr - disc_b.props.disc_nr

        disc_model_sort.set_sort_func(
            self._wrap_list_store_sort_func(_disc_order_sort))

        self._grilo.get_album_discs(media, disc_model)

        return disc_model_sort

    def get_artist_album_model(self, media):
        albums_model_filter = Dazzle.ListModelFilter.new(self._album_model)
        albums_model_filter.set_filter_func(lambda a: False)

        albums_model_sort = Gfm.SortListModel.new(albums_model_filter)

        self._grilo.get_artist_albums(media, albums_model_filter)

        def _album_sort(album_a, album_b):
            return album_a.props.year > album_b.props.year

        albums_model_sort.set_sort_func(
            self._wrap_list_store_sort_func(_album_sort))

        return albums_model_sort

    def set_playlist_model(self, playlist_type, model):

        def _on_items_changed(model, position, removed, added):
            if removed > 0:
                for i in list(range(removed)):
                    self._playlist_model.remove(position)

            if added > 0:
                for i in list(range(added)):
                    coresong = model[position + i]
                    song = CoreSong(
                        coresong.props.media, self._coreselection,
                        self._grilo)

                    self._playlist_model.insert(position + i, song)

                    song.bind_property(
                        "state", coresong, "state",
                        GObject.BindingFlags.SYNC_CREATE)

        with model.freeze_notify():

            if playlist_type == PlayerPlaylist.Type.ALBUM:

                self._playlist_model.remove_all()
                proxy_model = Gio.ListStore.new(Gio.ListModel)

                for disc in model:
                    proxy_model.append(disc.props.model)

                self._flatten_model = Gfm.FlattenListModel.new(
                    CoreSong, proxy_model)
                self._flatten_model.connect("items-changed", _on_items_changed)

                for model_song in self._flatten_model:
                    song = CoreSong(
                        model_song.props.media, self._coreselection,
                        self._grilo)

                    self._playlist_model.append(song)
                    song.bind_property(
                        "state", model_song, "state",
                        GObject.BindingFlags.SYNC_CREATE)

                self.emit("playlist-loaded")
            elif playlist_type == PlayerPlaylist.Type.ARTIST:
                self._playlist_model.remove_all()
                proxy_model = Gio.ListStore.new(Gio.ListModel)

                for artist_album in model:
                    for disc in artist_album.model:
                        proxy_model.append(disc.props.model)

                self._flatten_model = Gfm.FlattenListModel.new(
                    CoreSong, proxy_model)
                self._flatten_model.connect("items-changed", _on_items_changed)

                for model_song in self._flatten_model:
                    song = CoreSong(
                        model_song.props.media, self._coreselection,
                        self._grilo)

                    self._playlist_model.append(song)
                    song.bind_property(
                        "state", model_song, "state",
                        GObject.BindingFlags.SYNC_CREATE)

                self.emit("playlist-loaded")
            elif playlist_type == PlayerPlaylist.Type.SONGS:
                if self._song_signal_id:
                    self._songliststore.props.model.disconnect(
                        self._song_signal_id)

                self._playlist_model.remove_all()

                for song in self._songliststore.props.model:
                    self._playlist_model.append(song)

                    if song.props.state == SongWidget.State.PLAYING:
                        song.props.state = SongWidget.State.PLAYED

                self._song_signal_id = self._songliststore.props.model.connect(
                    "items-changed", _on_items_changed)

                self.emit("playlist-loaded")
            elif playlist_type == PlayerPlaylist.Type.SEARCH_RESULT:
                if self._search_signal_id:
                    self._song_search_flatten.disconnect(
                        self._search_signal_id)

                self._playlist_model.remove_all()

                for song in self._song_search_flatten:
                    self._playlist_model.append(song)

                self._search_signal_id = self._song_search_flatten.connect(
                    "items-changed", _on_items_changed)

                self.emit("playlist-loaded")
            elif playlist_type == PlayerPlaylist.Type.PLAYLIST:
                # if self._search_signal_id:
                #     self._song_search_model.disconnect(self._search_signal_id)

                self._playlist_model.remove_all()

                for model_song in model:
                    song = CoreSong(
                        model_song.props.media, self._coreselection,
                        self._grilo)

                    self._playlist_model.append(song)

                    song.bind_property(
                        "state", model_song, "state",
                        GObject.BindingFlags.SYNC_CREATE)

                # self._search_signal_id = self._song_search_model.connect(
                #     "items-changed", _on_items_changed)

                self.emit("playlist-loaded")

    def stage_playlist_deletion(self, playlist):
        """Prepares playlist deletion.

        :param Playlist playlist: playlist
        """
        self._grilo.stage_playlist_deletion(playlist)

    def finish_playlist_deletion(self, playlist, deleted):
        """Finishes playlist deletion.

        :param Playlist playlist: playlist
        :param bool deleted: indicates if the playlist has been deleted
        """
        self._grilo.finish_playlist_deletion(playlist, deleted)

    def create_playlist(self, playlist_title, callback):
        """Creates a new user playlist.

        :param str playlist_title: playlist title
        :param callback: function to perform once, the playlist is created
        """
        self._grilo.create_playlist(playlist_title, callback)

    def search(self, text):
        self._grilo.search(text)

    @GObject.Property(
        type=Gio.ListStore, default=None, flags=GObject.ParamFlags.READABLE)
    def songs(self):
        return self._model

    @GObject.Property(
        type=Gio.ListStore, default=None, flags=GObject.ParamFlags.READABLE)
    def albums(self):
        return self._album_model

    @GObject.property(
        type=Gio.ListStore, default=None, flags=GObject.ParamFlags.READABLE)
    def artists(self):
        return self._artist_model

    @GObject.Property(
        type=Gio.ListStore, default=None, flags=GObject.ParamFlags.READABLE)
    def playlist(self):
        return self._playlist_model

    @GObject.Property(
        type=Gfm.SortListModel, default=None,
        flags=GObject.ParamFlags.READABLE)
    def albums_sort(self):
        return self._album_model_sort

    @GObject.property(
        type=Gfm.SortListModel, default=None,
        flags=GObject.ParamFlags.READABLE)
    def artists_sort(self):
        return self._artist_model_sort

    @GObject.Property(
        type=Gfm.SortListModel, default=None,
        flags=GObject.ParamFlags.READABLE)
    def playlist_sort(self):
        return self._playlist_model_sort

    @GObject.Property(
        type=Dazzle.ListModelFilter, default=None,
        flags=GObject.ParamFlags.READABLE)
    def songs_search(self):
        return self._song_search_flatten

    @GObject.Property(
        type=Gio.ListStore, default=None,
        flags=GObject.ParamFlags.READABLE)
    def songs_search_proxy(self):
        return self._song_search_proxy

    @GObject.Property(
        type=Dazzle.ListModelFilter, default=None,
        flags=GObject.ParamFlags.READABLE)
    def albums_search(self):
        return self._album_search_model

    @GObject.property(
        type=Dazzle.ListModelFilter, default=None,
        flags=GObject.ParamFlags.READABLE)
    def artists_search(self):
        return self._artist_search_model

    @GObject.Property(
        type=Gtk.ListStore, default=None, flags=GObject.ParamFlags.READABLE)
    def songs_gtkliststore(self):
        return self._songliststore

    @GObject.Property(
        type=Gio.ListStore, default=None, flags=GObject.ParamFlags.READABLE)
    def playlists(self):
        return self._playlists_model

    @GObject.Property(
        type=Gfm.SortListModel, default=None,
        flags=GObject.ParamFlags.READABLE)
    def playlists_sort(self):
        return self._playlists_model_sort

    @GObject.Property(
        type=Gfm.SortListModel, default=None,
        flags=GObject.ParamFlags.READABLE)
    def playlists_filter(self):
        return self._playlists_model_filter
