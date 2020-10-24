# Copyright 2019 The GNOME Music developers
#
# GNOME Music is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# GNOME Music is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with GNOME Music; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# The GNOME Music authors hereby grant permission for non-GPL compatible
# GStreamer plugins to be used and distributed together with GStreamer
# and GNOME Music.  This permission is above and beyond the permissions
# granted by the GPL license by which GNOME Music is covered.  If you
# modify this code, you may extend this exception to your version of the
# code, but you are not obligated to do so.  If you do not wish to do so,
# delete this exception statement from your version.

import gi
gi.require_versions({"Gfm": "0.1", "Grl": "0.3", "Tracker": "3.0"})
from gi.repository import Gfm, Gio, Grl, GLib, GObject, Tracker

from gnomemusic.corealbum import CoreAlbum
from gnomemusic.coreartist import CoreArtist
from gnomemusic.coredisc import CoreDisc
from gnomemusic.coresong import CoreSong
from gnomemusic.grilowrappers.grltrackerplaylists import GrlTrackerPlaylists
from gnomemusic.storeart import StoreArt


class GrlTrackerWrapper(GObject.GObject):
    """Wrapper for the Grilo Tracker source.
    """

    _SPLICE_SIZE = 100

    _METADATA_ALBUM_CHANGED_KEYS = [
        Grl.METADATA_KEY_ARTIST,
        Grl.METADATA_KEY_ALBUM_ARTIST,
        Grl.METADATA_KEY_COMPOSER,
        Grl.METADATA_KEY_CREATION_DATE,
        Grl.METADATA_KEY_ID,
        Grl.METADATA_KEY_TITLE,
        Grl.METADATA_KEY_URL
    ]

    _METADATA_SONG_FILL_KEYS = [
        Grl.METADATA_KEY_ALBUM,
        Grl.METADATA_KEY_ALBUM_DISC_NUMBER,
        Grl.METADATA_KEY_ARTIST,
        Grl.METADATA_KEY_DURATION,
        Grl.METADATA_KEY_FAVOURITE,
        Grl.METADATA_KEY_ID,
        Grl.METADATA_KEY_PLAY_COUNT,
        Grl.METADATA_KEY_TITLE,
        Grl.METADATA_KEY_TRACK_NUMBER,
        Grl.METADATA_KEY_URL
    ]

    _METADATA_SONG_MEDIA_QUERY_KEYS = [
        Grl.METADATA_KEY_ALBUM,
        Grl.METADATA_KEY_ALBUM_DISC_NUMBER,
        Grl.METADATA_KEY_ARTIST,
        Grl.METADATA_KEY_DURATION,
        Grl.METADATA_KEY_FAVOURITE,
        Grl.METADATA_KEY_ID,
        Grl.METADATA_KEY_PLAY_COUNT,
        Grl.METADATA_KEY_TITLE,
        Grl.METADATA_KEY_TRACK_NUMBER,
        Grl.METADATA_KEY_URL
    ]

    _METADATA_THUMBNAIL_KEYS = [
        Grl.METADATA_KEY_ID,
        Grl.METADATA_KEY_THUMBNAIL
    ]

    def __init__(self, source, application, tracker_wrapper):
        """Initialize the Tracker wrapper

        :param Grl.TrackerSource source: The Tracker source to wrap
        :param Application application: Application instance
        :param TrackerWrapper tracker_wrapper: The TrackerWrapper instance
        """
        super().__init__()

        self._application = application
        coremodel = application.props.coremodel
        self._log = application.props.log
        self._songs_model = Gio.ListStore.new(CoreSong)
        coremodel.props.songs_proxy.append(self._songs_model)
        self._source = None
        self._albums_model = Gio.ListStore.new(CoreAlbum)
        coremodel.props.albums_proxy.append(self._albums_model)
        self._album_ids = {}
        self._artists_model = Gio.ListStore.new(CoreArtist)
        coremodel.props.artists_proxy.append(self._artists_model)
        self._artist_ids = {}
        self._hash = {}
        self._song_search_proxy = coremodel.props.songs_search_proxy
        self._album_search_model = coremodel.props.albums_search
        self._artist_search_model = coremodel.props.artists_search
        self._batch_changed_media_ids = {}
        self._content_changed_timeout = 0
        self._tracker_playlists = None
        self._tracker_wrapper = tracker_wrapper
        self._notificationmanager = application.props.notificationmanager

        self._song_search_tracker = Gfm.FilterListModel.new(self._songs_model)
        self._song_search_tracker.set_filter_func(lambda a: False)
        self._song_search_proxy.append(self._song_search_tracker)

        self._fast_options = Grl.OperationOptions()
        self._fast_options.set_resolution_flags(
            Grl.ResolutionFlags.FAST_ONLY | Grl.ResolutionFlags.IDLE_RELAY)
        self._full_options = Grl.OperationOptions()
        self._full_options.set_resolution_flags(
            Grl.ResolutionFlags.FULL | Grl.ResolutionFlags.IDLE_RELAY)

        self._content_changed_id = 0
        self.props.source = source

        self._initial_songs_fill()
        self._initial_albums_fill()
        self._initial_artists_fill()

    @GObject.Property(type=Grl.Source, default=None)
    def source(self):
        return self._source

    @source.setter  # type: ignore
    def source(self, new_source):
        """Set a new grilo tracker source

        Everytime, the tracker plugin is loaded, a new source is
        created. The source needs to be updated to get notifications.

        :param Grl.Source new_source: new grilo tracker source
        """
        if self._content_changed_id != 0:
            self._source.disconnect(self._content_changed_id)
            self._content_changed_id = 0

        self._source = new_source
        self._source.notify_change_start()
        self._content_changed_id = self._source.connect(
            "content-changed", self._batch_content_changed)

    def _batch_content_changed(self, source, medias, change_type, loc_unknown):
        if medias == []:
            return

        if change_type not in self._batch_changed_media_ids.keys():
            self._batch_changed_media_ids[change_type] = []

        changed_medias = [
            media.get_id() for media in medias
            if media.is_audio() or media.is_container()]
        self._batch_changed_media_ids[change_type].extend(changed_medias)

        if self._content_changed_timeout == 0:
            self._content_changed_timeout = GLib.timeout_add(
                250, self._on_content_changed)

    def _on_content_changed(self):
        for change_type in self._batch_changed_media_ids.keys():
            media_ids = self._batch_changed_media_ids[change_type]

            # The Tracker indexed paths may differ from Music's paths.
            # In that case Tracker will report it as 'changed', while
            # it means 'added' to Music.
            if (change_type == Grl.SourceChangeType.CHANGED
                    or change_type == Grl.SourceChangeType.ADDED):
                self._log.debug(
                    "Added/Changed media(s): {}".format(media_ids))
                self._changed_media(media_ids)
            elif change_type == Grl.SourceChangeType.REMOVED:
                self._log.debug(
                    "Removed media(s): {}".format(media_ids))
                self._remove_media(media_ids)

        self._check_album_change()
        self._check_artist_change()
        if self._tracker_playlists is not None:
            self._tracker_playlists.check_smart_playlist_change()

        self._batch_changed_media_ids = {}
        self._content_changed_timeout = 0

        return GLib.SOURCE_REMOVE

    def _check_album_change(self):
        album_ids = {}

        query = """
        SELECT
            ?type ?id ?title ?composer ?albumArtist
            ?artist ?url ?creationDate
        WHERE {
            SERVICE <dbus:%(miner_fs_busname)s> {
                GRAPH tracker:Audio {
                    SELECT
                        %(media_type)s AS ?type
                        ?album AS ?id
                        nie:title(?album) AS ?title
                        ?composer
                        ?albumArtist
                        nmm:artistName(?artist) AS ?artist
                        nie:isStoredAs(?song) AS ?url
                        YEAR(MAX(nie:contentCreated(?song))) AS ?creationDate
                    WHERE {
                        ?album a nmm:MusicAlbum .
                        ?song a nmm:MusicPiece ;
                                nmm:musicAlbum ?album ;
                                nmm:artist ?artist .
                        OPTIONAL { ?song nmm:composer/
                                         nmm:artistName ?composer . }
                        OPTIONAL { ?album nmm:albumArtist/
                                          nmm:artistName ?albumArtist . }
                        %(location_filter)s
                    } GROUP BY ?album
                }
            }
        }
        """.replace('\n', ' ').strip() % {
            "miner_fs_busname": self._tracker_wrapper.props.miner_fs_busname,
            "media_type": int(Grl.MediaType.CONTAINER),
            'location_filter': self._tracker_wrapper.location_filter()
        }

        def check_album_cb(source, op_id, media, remaining, error):
            if error:
                self._log.warning("Error: {}".format(error))
                return

            if not media:
                changed_ids = set(
                    album_ids.keys()) ^ set(self._album_ids.keys())

                self._log.debug(
                    "Albums changed ID's: {}".format(changed_ids))

                for key in changed_ids:
                    if key in album_ids:
                        self._albums_model.append(album_ids[key])
                    elif key in self._album_ids:
                        for idx, corealbum in enumerate(self._albums_model):
                            if corealbum.media.get_id() == key:
                                self._albums_model.remove(idx)
                                break

                self._album_ids = album_ids
                return

            if media.get_id() in self._album_ids.keys():
                album = self._album_ids[media.get_id()]
            else:
                album = CoreAlbum(self._application, media)

            album_ids[media.get_id()] = album

        self.props.source.query(
            query, self._METADATA_ALBUM_CHANGED_KEYS, self._fast_options,
            check_album_cb)

    def _check_artist_change(self):
        artist_ids = {}

        query = """
        SELECT ?type ?id ?artist
        WHERE {
            SERVICE <dbus:%(miner_fs_busname)s> {
                GRAPH tracker:Audio {
                    SELECT
                        %(media_type)s AS ?type
                        (COALESCE(?album_artist, ?artist) AS ?id)
                        ?artist_bind AS ?artist
                    WHERE {
                        ?song a nmm:MusicPiece;
                                nmm:musicAlbum ?album;
                                nmm:artist ?artist .
                        OPTIONAL {
                            ?album a nmm:MusicAlbum;
                                     nmm:albumArtist ?album_artist .
                        }
                        BIND(COALESCE(nmm:artistName(?album_artist),
                                      nmm:artistName(?artist)) AS ?artist_bind)
                        %(location_filter)s
                    }
                    GROUP BY ?artist_bind
                }
            }
        }
        """.replace('\n', ' ').strip() % {
            "miner_fs_busname": self._tracker_wrapper.props.miner_fs_busname,
            "media_type": int(Grl.MediaType.CONTAINER),
            'location_filter': self._tracker_wrapper.location_filter()
        }

        metadata_keys = [
            Grl.METADATA_KEY_ALBUM_ARTIST,
            Grl.METADATA_KEY_ARTIST,
            Grl.METADATA_KEY_ID
        ]

        def check_artist_cb(source, op_id, media, remaining, error):
            if error:
                self._log.warning("Error: {}".format(error))
                return

            if not media:
                changed_ids = set(
                    artist_ids.keys()) ^ set(self._artist_ids.keys())
                self._log.debug(
                    "Artists changed ID's: {}".format(changed_ids))

                for key in changed_ids:
                    if key in artist_ids:
                        self._artists_model.append(artist_ids[key])
                    elif key in self._artist_ids:
                        for idx, coreartist in enumerate(self._artists_model):
                            if coreartist.media.get_id() == key:
                                self._artists_model.remove(idx)
                                break

                self._artist_ids = artist_ids
                return

            if media.get_id() in self._artist_ids.keys():
                artist = self._artist_ids[media.get_id()]
            else:
                artist = CoreArtist(self._application, media)

            artist_ids[media.get_id()] = artist

        self.props.source.query(
            query, metadata_keys, self._fast_options, check_artist_cb)

    def _remove_media(self, media_ids):
        for media_id in media_ids:
            try:
                coresong = self._hash.pop(media_id)
            except KeyError:
                self._log.warning("Removal KeyError.")
                return

            for idx, coresong_model in enumerate(self._songs_model):
                if coresong_model is coresong:
                    self._log.debug("Removing: {}, {}".format(
                        coresong.props.media.get_id(), coresong.props.title))

                    self._songs_model.remove(idx)
                    break

    def _song_media_query(self, media_ids):
        media_ids = str(media_ids)[1:-1]

        query = """
        SELECT
            ?type ?urn ?title ?id ?url
            ?artist ?album
            ?duration ?trackNumber
            ?albumDiscNumber
            nie:usageCounter(?urn) AS ?playCount
            ?tag AS ?favorite
        WHERE {
            SERVICE <dbus:%(miner_fs_busname)s> {
                GRAPH tracker:Audio {
                    SELECT DISTINCT
                        %(media_type)s AS ?type
                        ?song AS ?urn
                        nie:title(?song) AS ?title
                        ?song AS ?id
                        nie:isStoredAs(?song) AS ?url
                        nmm:artistName(nmm:artist(?song)) AS ?artist
                        nie:title(nmm:musicAlbum(?song)) AS ?album
                        nfo:duration(?song) AS ?duration
                        nmm:trackNumber(?song) AS ?trackNumber
                        nmm:setNumber(nmm:musicAlbumDisc(?song))
                            AS ?albumDiscNumber
                    WHERE {
                        ?song a nmm:MusicPiece .
                        FILTER ( ?song in ( %(media_ids)s ) )
                        %(location_filter)s
                    }
                }
            }
            OPTIONAL {
                ?urn nao:hasTag ?tag .
                FILTER (?tag = nao:predefined-tag-favorite)
            }
        }
        """.replace('\n', ' ').strip() % {
            "miner_fs_busname": self._tracker_wrapper.props.miner_fs_busname,
            "media_type": int(Grl.MediaType.AUDIO),
            'location_filter': self._tracker_wrapper.location_filter(),
            'media_ids': media_ids
        }

        return query

    def _changed_media(self, media_ids):

        def _update_changed_media(source, op_id, media, remaining, error):
            if error:
                self._log.warning("Error: {}".format(error))
                return

            if not media:
                self._remove_media(media_ids)
                return

            media_id = media.get_id()
            if media_id not in self._hash:
                song = CoreSong(self._application, media)
                self._songs_model.append(song)
                self._hash[media_id] = song
                self._log.debug(
                    "Adding: {}, {}".format(media_id, song.props.title))
            else:
                self._hash[media_id].update(media)

            media_ids.remove(media_id)

        self.props.source.query(
            self._song_media_query(media_ids),
            self._METADATA_SONG_MEDIA_QUERY_KEYS, self._fast_options,
            _update_changed_media)

    def _initial_songs_fill(self):
        self._notificationmanager.push_loading()
        songs_added = []

        def _add_to_model(source, op_id, media, remaining, error):
            if error:
                self._log.warning("Error: {}".format(error))
                self._notificationmanager.pop_loading()
                return

            if not media:
                self._songs_model.splice(
                    self._songs_model.get_n_items(), 0, songs_added)
                self._notificationmanager.pop_loading()

                # Initialize the playlists subwrapper after the initial
                # songs model fill, the playlists expect a filled songs
                # hashtable.
                self._tracker_playlists = GrlTrackerPlaylists(
                    self.props.source, self._application,
                    self._tracker_wrapper, self._hash)

                return

            song = CoreSong(self._application, media)
            songs_added.append(song)
            self._hash[media.get_id()] = song
            if len(songs_added) == self._SPLICE_SIZE:
                self._songs_model.splice(
                    self._songs_model.get_n_items(), 0, songs_added)
                songs_added.clear()

        query = """
        SELECT
            ?type ?urn ?title ?id ?url
            ?artist ?album
            ?duration ?trackNumber
            ?albumDiscNumber
            nie:usageCounter(?urn) AS ?playCount
            ?tag AS ?favorite
        WHERE {
            SERVICE <dbus:%(miner_fs_busname)s> {
                GRAPH tracker:Audio {
                    SELECT
                        %(media_type)s AS ?type
                        ?song AS ?urn
                        nie:title(?song) AS ?title
                        ?song AS ?id
                        nie:isStoredAs(?song) AS ?url
                        nmm:artistName(nmm:artist(?song)) AS ?artist
                        nie:title(nmm:musicAlbum(?song)) AS ?album
                        nfo:duration(?song) AS ?duration
                        nmm:trackNumber(?song) AS ?trackNumber
                        nmm:setNumber(nmm:musicAlbumDisc(?song))
                            AS ?albumDiscNumber
                    WHERE {
                        ?song a nmm:MusicPiece .
                        %(location_filter)s
                    }
                    ORDER BY ?title
                }
            }
            OPTIONAL {
                ?urn nao:hasTag ?tag .
                FILTER (?tag = nao:predefined-tag-favorite)
            }
        }
        """.replace('\n', ' ').strip() % {
            "miner_fs_busname": self._tracker_wrapper.props.miner_fs_busname,
            "media_type": int(Grl.MediaType.AUDIO),
            'location_filter': self._tracker_wrapper.location_filter()
        }

        self.props.source.query(
            query, self._METADATA_SONG_FILL_KEYS, self._fast_options,
            _add_to_model)

    def _initial_albums_fill(self):
        self._notificationmanager.push_loading()
        albums_added = []

        def _add_to_albums_model(source, op_id, media, remaining, error):
            if error:
                self._log.warning("Error: {}".format(error))
                self._notificationmanager.pop_loading()
                return

            if not media:
                self._albums_model.splice(
                    self._albums_model.get_n_items(), 0, albums_added)
                self._notificationmanager.pop_loading()
                return

            album = CoreAlbum(self._application, media)
            self._album_ids[media.get_id()] = album
            albums_added.append(album)
            if len(albums_added) == self._SPLICE_SIZE:
                self._albums_model.splice(
                    self._albums_model.get_n_items(), 0, albums_added)
                albums_added.clear()

        query = """
        SELECT
            ?type ?id ?title ?composer ?albumArtist
            ?artist ?url ?creationDate
        WHERE
        {
            SERVICE <dbus:%(miner_fs_busname)s> {
                GRAPH tracker:Audio {
                    SELECT
                        %(media_type)s AS ?type
                        ?album AS ?id
                        nie:title(?album) AS ?title
                        ?composer
                        ?albumArtist
                        nmm:artistName(?artist) AS ?artist
                        nie:isStoredAs(?song) AS ?url
                        YEAR(MAX(nie:contentCreated(?song))) AS ?creationDate
                    WHERE
                    {
                        ?album a nmm:MusicAlbum .
                        ?song a nmm:MusicPiece ;
                                nmm:musicAlbum ?album ;
                                nmm:artist ?artist .
                        OPTIONAL { ?song nmm:composer/
                                         nmm:artistName ?composer . }
                        OPTIONAL { ?album nmm:albumArtist/
                                          nmm:artistName ?albumArtist . }
                        %(location_filter)s
                    }
                    GROUP BY ?album
                    ORDER BY ?title ?albumArtist ?artist ?creationDate
                }
            }
        }
        """.replace('\n', ' ').strip() % {
            "miner_fs_busname": self._tracker_wrapper.props.miner_fs_busname,
            "media_type": int(Grl.MediaType.CONTAINER),
            'location_filter': self._tracker_wrapper.location_filter()
        }

        self.props.source.query(
            query, self._METADATA_ALBUM_CHANGED_KEYS, self._fast_options,
            _add_to_albums_model)

    def _initial_artists_fill(self):
        self._notificationmanager.push_loading()
        artists_added = []

        def _add_to_artists_model(source, op_id, media, remaining, error):
            if error:
                self._log.warning("Error: {}".format(error))
                self._notificationmanager.pop_loading()
                return

            if not media:
                self._artists_model.splice(
                    self._artists_model.get_n_items(), 0, artists_added)
                self._notificationmanager.pop_loading()
                return

            artist = CoreArtist(self._application, media)
            self._artist_ids[media.get_id()] = artist
            artists_added.append(artist)
            if len(artists_added) == self._SPLICE_SIZE:
                self._artists_model.splice(
                    self._artists_model.get_n_items(), 0, artists_added)
                artists_added.clear()

        query = """
        SELECT ?type ?id ?artist
        WHERE {
            SERVICE <dbus:%(miner_fs_busname)s> {
                GRAPH tracker:Audio {
                    SELECT
                       %(media_type)s AS ?type
                       (COALESCE(?album_artist, ?artist) AS ?id)
                       ?artist_bind AS ?artist
                    WHERE {
                        ?song a nmm:MusicPiece;
                                nmm:musicAlbum ?album;
                                nmm:artist ?artist .
                        OPTIONAL {
                            ?album a nmm:MusicAlbum;
                                     nmm:albumArtist ?album_artist .
                        }
                        BIND(COALESCE(nmm:artistName(?album_artist),
                                      nmm:artistName(?artist)) AS ?artist_bind)
                        %(location_filter)s
                    }
                    GROUP BY ?artist_bind
                    ORDER BY ?artist_bind
                }
            }
        }
        """.replace('\n', ' ').strip() % {
            "miner_fs_busname": self._tracker_wrapper.props.miner_fs_busname,
            "media_type": int(Grl.MediaType.CONTAINER),
            'location_filter': self._tracker_wrapper.location_filter()
        }

        metadata_keys = [
            Grl.METADATA_KEY_ARTIST,
            Grl.METADATA_KEY_ID
        ]

        self.props.source.query(
            query, metadata_keys, self._fast_options, _add_to_artists_model)

    def get_artist_albums(self, media, model):
        """Get all albums by an artist

        :param Grl.Media media: The media with the artist id
        :param Gfm.FilterListModel model: The model to fill
        """
        self._notificationmanager.push_loading()
        artist_id = media.get_id()

        query = """
        SELECT
            ?type ?id ?title ?creationDate
        WHERE {
            SERVICE <dbus:%(miner_fs_busname)s> {
                GRAPH tracker:Audio {
                    SELECT DISTINCT
                        %(media_type)s AS ?type
                        ?album AS ?id
                        nie:title(?album) AS ?title
                        nie:contentCreated(?song) AS ?creationDate
                    WHERE {
                        ?album a nmm:MusicAlbum .
                        OPTIONAL { ?album  nmm:albumArtist ?album_artist . }
                        ?song a nmm:MusicPiece;
                              nmm:musicAlbum ?album;
                              nmm:artist ?artist .
                        FILTER ( ?album_artist = <%(artist_id)s>
                                 || ?artist = <%(artist_id)s> )
                        %(location_filter)s
                    }
                   GROUP BY ?album
                   ORDER BY ?creationDate ?album
                }
            }
        }
        """.replace('\n', ' ').strip() % {
            "miner_fs_busname": self._tracker_wrapper.props.miner_fs_busname,
            "media_type": int(Grl.MediaType.CONTAINER),
            "artist_id": artist_id,
            'location_filter': self._tracker_wrapper.location_filter()
        }

        albums = []

        def query_cb(source, op_id, media, remaining, error):
            if error:
                self._log.warning("Error: {}".format(error))
                self._notificationmanager.pop_loading()
                return

            if not media:
                model.set_filter_func(albums_filter, albums)
                self._notificationmanager.pop_loading()
                return

            albums.append(media)

        def albums_filter(corealbum, albums):
            for media in albums:
                if media.get_id() == corealbum.props.media.get_id():
                    return True

            return False

        self.props.source.query(
            query, [Grl.METADATA_KEY_TITLE], self._fast_options, query_cb)

    def get_album_discs(self, media, disc_model):
        """Get all discs of an album

        :param Grl.Media media: The media with the album id
        :param Gfm.SortListModel disc_model: The model to fill
        """
        self._notificationmanager.push_loading()
        album_id = media.get_id()

        query = """
        SELECT
            ?type ?id ?albumDiscNumber
        WHERE {
            SERVICE <dbus:%(miner_fs_busname)s> {
                GRAPH tracker:Audio {
                    SELECT DISTINCT
                        %(media_type)s AS ?type
                        ?album AS ?id
                        nmm:setNumber(nmm:musicAlbumDisc(?song))
                            AS ?albumDiscNumber
                    WHERE {
                        ?song a nmm:MusicPiece;
                                nmm:musicAlbum ?album .
                        FILTER ( ?album = <%(album_id)s> )
                        %(location_filter)s
                    }
                    ORDER BY ?albumDiscNumber
                }
            }
        }
        """.replace('\n', ' ').strip() % {
            "miner_fs_busname": self._tracker_wrapper.props.miner_fs_busname,
            "media_type": int(Grl.MediaType.CONTAINER),
            "album_id": album_id,
            'location_filter': self._tracker_wrapper.location_filter()
        }

        def _disc_nr_cb(source, op_id, media, remaining, error):
            if error:
                self._log.warning("Error: {}".format(error))
                self._notificationmanager.pop_loading()
                return

            if not media:
                self._notificationmanager.pop_loading()
                return

            disc_nr = media.get_album_disc_number()
            coredisc = CoreDisc(self._application, media, disc_nr)
            disc_model.append(coredisc)

        self.props.source.query(
            query, [Grl.METADATA_KEY_ALBUM_DISC_NUMBER], self._fast_options,
            _disc_nr_cb)

    def populate_album_disc_songs(self, media, disc_nr, callback):
        # FIXME: Pass a model and fill it.
        # FIXME: The query is similar to the other song queries, reuse
        # if possible.
        """Get all songs of an album disc

        :param Grl.Media media: The media with the album id
        :param int disc_nr: The disc number
        :param callback: The callback to call for every song added
        """
        album_id = media.get_id()

        query = """
        SELECT
            ?type ?id ?url ?title
            ?artist ?album
            ?duration ?trackNumber ?albumDiscNumber
            ?creationDate
            nie:usageCounter(?id) AS ?playCount
            ?tag AS ?favorite
        WHERE {
            SERVICE <dbus:%(miner_fs_busname)s> {
                GRAPH tracker:Audio {
                    SELECT DISTINCT
                        %(media_type)s AS ?type
                        ?song AS ?id
                        nie:isStoredAs(?song) AS ?url
                        nie:title(?song) AS ?title
                        nmm:artistName(nmm:artist(?song)) AS ?artist
                        nie:title(nmm:musicAlbum(?song)) AS ?album
                        nfo:duration(?song) AS ?duration
                        nmm:trackNumber(?song) AS ?trackNumber
                        nmm:setNumber(nmm:musicAlbumDisc(?song))
                            AS ?albumDiscNumber
                        YEAR(?date) AS ?creationDate
                    WHERE {
                        ?song a nmm:MusicPiece ;
                                nmm:musicAlbum ?album .
                        OPTIONAL { ?song nie:contentCreated ?date . }
                        FILTER (
                            ?album = <%(album_id)s> &&
                            nmm:setNumber(nmm:musicAlbumDisc(?song)) =
                                %(disc_nr)s
                        )
                        %(location_filter)s
                    }
                    ORDER BY ?trackNumber
                }
            }
            OPTIONAL {
                ?id nao:hasTag ?tag .
                FILTER (?tag = nao:predefined-tag-favorite)
            }
        }
        """.replace('\n', ' ').strip() % {
            "media_type": int(Grl.MediaType.AUDIO),
            'album_id': album_id,
            'disc_nr': disc_nr,
            'location_filter': self._tracker_wrapper.location_filter(),
            'miner_fs_busname': self._tracker_wrapper.props.miner_fs_busname
        }

        metadata_keys = [
            Grl.METADATA_KEY_ALBUM,
            Grl.METADATA_KEY_ALBUM_DISC_NUMBER,
            Grl.METADATA_KEY_ARTIST,
            Grl.METADATA_KEY_DURATION,
            Grl.METADATA_KEY_FAVOURITE,
            Grl.METADATA_KEY_ID,
            Grl.METADATA_KEY_PLAY_COUNT,
            Grl.METADATA_KEY_TITLE,
            Grl.METADATA_KEY_URL
        ]

        self.props.source.query(
            query, metadata_keys, self._fast_options, callback)

    def search(self, text):
        # FIXME: Searches are limited to not bog down the UI with
        # widget creation ({List,Flow}Box limitations). The limit is
        # arbitrarily set to 50 and set in the Tracker query. It should
        # be possible to set it through Grilo options instead. This
        # does not work as expected and needs further investigation.
        term = Tracker.sparql_escape_string(
            GLib.utf8_normalize(
                GLib.utf8_casefold(text, -1), -1, GLib.NormalizeMode.NFKD))

        # Artist search
        self._notificationmanager.push_loading()

        query = """
        SELECT
            ?type ?id
        WHERE {
            SERVICE <dbus:%(miner_fs_busname)s> {
                GRAPH tracker:Audio {
                    SELECT DISTINCT
                        %(media_type)s AS ?type
                        COALESCE(?album_artist, ?artist) AS ?id
                    WHERE {
                        ?song a nmm:MusicPiece ;
                                nmm:musicAlbum ?album ;
                                nmm:artist ?artist .
                        OPTIONAL {
                            ?album a nmm:MusicAlbum ;
                                     nmm:albumArtist ?album_artist .
                        }
                        BIND(COALESCE(nmm:artistName(?album_artist),
                                      nmm:artistName(?artist)) AS ?artist_bind)
                        BIND(tracker:normalize(nmm:artistName(
                                 nmm:albumArtist(?artist_bind)), 'nfkd')
                             AS ?match1) .
                        BIND(tracker:normalize(
                                 nmm:artistName(nmm:artist(?song)), 'nfkd')
                             AS ?match2) .
                        BIND(tracker:normalize(nmm:composer(?song), 'nfkd')
                             AS ?match4) .
                        FILTER (
                            CONTAINS(tracker:case-fold(
                                tracker:unaccent(?match1)), "%(name)s")
                            || CONTAINS(tracker:case-fold(?match1), "%(name)s")
                            || CONTAINS(tracker:case-fold(
                                tracker:unaccent(?match2)), "%(name)s")
                            || CONTAINS(tracker:case-fold(?match2), "%(name)s")
                            || CONTAINS(tracker:case-fold(
                                tracker:unaccent(?match4)), "%(name)s")
                            || CONTAINS(tracker:case-fold(?match4), "%(name)s")
                        )
                        %(location_filter)s
                    }
                    LIMIT 50
                }
            }
        }
        """.replace('\n', ' ').strip() % {
            "miner_fs_busname": self._tracker_wrapper.props.miner_fs_busname,
            "media_type": int(Grl.MediaType.AUDIO),
            'location_filter': self._tracker_wrapper.location_filter(),
            'name': term
        }

        artist_filter_ids = []

        def artist_filter(coreartist):
            return coreartist.media.get_id() in artist_filter_ids

        def artist_search_cb(source, op_id, media, remaining, error):
            if error:
                self._log.warning("Error: {}".format(error))
                self._notificationmanager.pop_loading()
                return

            if not media:
                self._artist_search_model.set_filter_func(artist_filter)
                self._notificationmanager.pop_loading()
                return

            artist_filter_ids.append(media.get_id())

        self.props.source.query(
            query, [Grl.METADATA_KEY_ID], self._fast_options, artist_search_cb)

        # Album search
        self._notificationmanager.push_loading()

        query = """
        SELECT
            ?type ?id
        WHERE {
            SERVICE <dbus:%(miner_fs_busname)s> {
                GRAPH tracker:Audio {
                    SELECT DISTINCT
                        %(media_type)s AS ?type
                        nmm:musicAlbum(?song) AS ?id
                    WHERE {
                        ?song a nmm:MusicPiece .
                        BIND(tracker:normalize(
                                 nie:title(nmm:musicAlbum(?song)), 'nfkd')
                             AS ?match1) .
                        BIND(tracker:normalize(
                                 nmm:artistName(nmm:artist(?song)), 'nfkd')
                             AS ?match2) .
                        BIND(tracker:normalize(nmm:composer(?song), 'nfkd')
                             AS ?match4) .
                        FILTER (
                            CONTAINS(tracker:case-fold(
                                tracker:unaccent(?match1)), "%(name)s")
                            || CONTAINS(tracker:case-fold(?match1), "%(name)s")
                            || CONTAINS(tracker:case-fold(
                                tracker:unaccent(?match2)), "%(name)s")
                            || CONTAINS(tracker:case-fold(?match2), "%(name)s")
                            || CONTAINS(tracker:case-fold(
                                tracker:unaccent(?match4)), "%(name)s")
                            || CONTAINS(tracker:case-fold(?match4), "%(name)s")
                        )
                        %(location_filter)s
                    }
                    LIMIT 50
                }
            }
        }
        """.replace('\n', ' ').strip() % {
            "miner_fs_busname": self._tracker_wrapper.props.miner_fs_busname,
            "media_type": int(Grl.MediaType.CONTAINER),
            'location_filter': self._tracker_wrapper.location_filter(),
            'name': term
        }

        album_filter_ids = []

        def album_filter(corealbum):
            return corealbum.media.get_id() in album_filter_ids

        def albums_search_cb(source, op_id, media, remaining, error):
            if error:
                self._log.warning("Error: {}".format(error))
                self._notificationmanager.pop_loading()
                return

            if not media:
                self._album_search_model.set_filter_func(album_filter)
                self._notificationmanager.pop_loading()
                return

            album_filter_ids.append(media.get_id())

        self.props.source.query(
            query, [Grl.METADATA_KEY_ID], self._fast_options, albums_search_cb)

        # Song search
        self._notificationmanager.push_loading()

        query = """
        SELECT
            ?type ?id
        WHERE {
            SERVICE <dbus:%(miner_fs_busname)s> {
                GRAPH tracker:Audio {
                    SELECT DISTINCT
                        %(media_type)s AS ?type
                        ?song AS ?id
                    WHERE {
                        ?song a nmm:MusicPiece .
                        BIND(tracker:normalize(
                                 nie:title(nmm:musicAlbum(?song)), 'nfkd')
                             AS ?match1) .
                        BIND(tracker:normalize(
                                 nmm:artistName(nmm:artist(?song)), 'nfkd')
                             AS ?match2) .
                        BIND(tracker:normalize(
                            nie:title(?song), 'nfkd') AS ?match3) .
                        BIND(tracker:normalize(nmm:composer(?song), 'nfkd')
                             AS ?match4) .
                        FILTER (
                            CONTAINS(tracker:case-fold(
                                tracker:unaccent(?match1)), "%(name)s")
                            || CONTAINS(tracker:case-fold(?match1), "%(name)s")
                            || CONTAINS(tracker:case-fold(
                                tracker:unaccent(?match2)), "%(name)s")
                            || CONTAINS(tracker:case-fold(?match2), "%(name)s")
                            || CONTAINS(tracker:case-fold(
                                tracker:unaccent(?match3)), "%(name)s")
                            || CONTAINS(tracker:case-fold(?match3), "%(name)s")
                            || CONTAINS(tracker:case-fold(
                                tracker:unaccent(?match4)), "%(name)s")
                            || CONTAINS(tracker:case-fold(?match4), "%(name)s")
                        )
                        %(location_filter)s
                    }
                    LIMIT 50
                }
            }
        }
        """.replace('\n', ' ').strip() % {
            "miner_fs_busname": self._tracker_wrapper.props.miner_fs_busname,
            "media_type": int(Grl.MediaType.AUDIO),
            'location_filter': self._tracker_wrapper.location_filter(),
            'name': term
        }

        filter_ids = []

        def songs_filter(coresong):
            return coresong.media.get_id() in filter_ids

        def songs_search_cb(source, op_id, media, remaining, error):
            if error:
                self._log.warning("Error: {}".format(error))
                self._notificationmanager.pop_loading()
                return

            if not media:
                self._song_search_tracker.set_filter_func(songs_filter)
                self._notificationmanager.pop_loading()
                return

            filter_ids.append(media.get_id())

        self.props.source.query(
            query, [Grl.METADATA_KEY_ID], self._fast_options, songs_search_cb)

    def _get_album_for_media_id_query(self, media_id, song=True):
        # Even though we check for the album_artist, we fill
        # the artist key, since Grilo coverart plugins use
        # only that key for retrieval.

        if song:
            filter_clause = "?song = <{}>".format(str(media_id))
        else:
            filter_clause = "?album = <{}>".format(str(media_id))

        query = """
        SELECT
            ?type ?id ?mbReleaseGroup ?mbRelease ?artist ?album
        WHERE {
            SERVICE <dbus:%(miner_fs_busname)s> {
                GRAPH tracker:Audio {
                    SELECT DISTINCT
                        %(media_type)s AS ?type
                        ?album AS ?id
                        tracker:referenceIdentifier(?release_group_id)
                            AS ?mbReleaseGroup
                        tracker:referenceIdentifier(?release_id) AS ?mbRelease
                        tracker:coalesce(nmm:artistName(?album_artist),
                                         nmm:artistName(?song_artist))
                            AS ?artist
                        nie:title(?album) AS ?album
                    WHERE {
                        ?album a nmm:MusicAlbum .
                        ?song a nmm:MusicPiece ;
                                nmm:musicAlbum ?album ;
                                nmm:artist ?song_artist .
                        OPTIONAL {
                            ?album tracker:hasExternalReference
                                ?release_group_id .
                            ?release_group_id tracker:referenceSource
                                "https://musicbrainz.org/doc/Release_Group" .
                        }
                        OPTIONAL {
                            ?album tracker:hasExternalReference ?release_id .
                            ?release_id tracker:referenceSource
                                "https://musicbrainz.org/doc/Release" .
                        }
                        OPTIONAL { ?album nmm:albumArtist ?album_artist . }
                        FILTER (
                            %(filter_clause)s
                        )
                        %(location_filter)s
                    }
                }
            }
        }
        """.replace("\n", " ").strip() % {
            "miner_fs_busname": self._tracker_wrapper.props.miner_fs_busname,
            "media_type": int(Grl.MediaType.CONTAINER),
            "filter_clause": filter_clause,
            "location_filter": self._tracker_wrapper.location_filter()
        }

        return query

    def get_song_art(self, coresong):
        """Retrieve song art for the given CoreSong

        Since MediaArt does not really support per-song art this
        uses the songs album information as base to retrieve relevant
        art and store it.

        :param CoreSong coresong: CoreSong to get art for
        """
        media = coresong.props.media

        # If there is no album and artist do not go through with the
        # query, it will not give any results.
        if (media.get_album() is None
                and (media.get_album_artist() is None
                     or media.get_artist() is None)):
            coresong.props.thumbnail = "generic"
            return

        def art_retrieved_cb(source, op_id, queried_media, remaining, error):
            if error:
                self._log.warning("Error: {}".format(error))
                coresong.props.thumbnail = "generic"
                return

            if queried_media is None:
                coresong.props.thumbnail = "generic"
                return

            StoreArt(coresong, queried_media.get_thumbnail())

        song_id = media.get_id()
        query = self._get_album_for_media_id_query(song_id)

        self.props.source.query(
            query, self._METADATA_THUMBNAIL_KEYS, self._full_options,
            art_retrieved_cb)

    def get_album_art(self, corealbum):
        """Retrieve album art for the given CoreAlbum

        :param CoreAlbum corealbum: CoreAlbum to get art for
        """
        media = corealbum.props.media

        def art_retrieved_cb(source, op_id, queried_media, remaining, error):
            if error:
                self._log.warning("Error: {}".format(error))
                corealbum.props.thumbnail = "generic"
                return

            if queried_media is None:
                corealbum.props.thumbnail = "generic"
                return

            StoreArt(corealbum, queried_media.get_thumbnail())

        album_id = media.get_id()
        query = self._get_album_for_media_id_query(album_id, False)

        self._source.query(
            query, self._METADATA_THUMBNAIL_KEYS, self._full_options,
            art_retrieved_cb)

    def get_artist_art(self, coreartist):
        """Retrieve artist art for the given CoreArtist

        This retrieves art through Grilo online services only.

        :param CoreArtist coreartist: CoreArtist to get art for
        """
        media = coreartist.props.media

        def art_resolved_cb(source, op_id, resolved_media, error):
            if error:
                self._log.warning("Error: {}".format(error))
                coreartist.props.thumbnail = "generic"
                return

            if resolved_media is None:
                coreartist.props.thumbnail = "generic"
                return

            StoreArt(coreartist, resolved_media.get_thumbnail())

        self.props.source.resolve(
            media, [Grl.METADATA_KEY_THUMBNAIL], self._full_options,
            art_resolved_cb)

    def stage_playlist_deletion(self, playlist):
        """Prepares playlist deletion.

        :param Playlist playlist: playlist
        """
        if self._tracker_playlists is None:
            return

        self._tracker_playlists.stage_playlist_deletion(playlist)

    def finish_playlist_deletion(self, playlist, deleted):
        """Finishes playlist deletion.

        :param Playlist playlist: playlist
        :param bool deleted: indicates if the playlist has been deleted
        """
        if self._tracker_playlists is None:
            return

        self._tracker_playlists.finish_playlist_deletion(playlist, deleted)

    def create_playlist(self, playlist_title, callback):
        """Creates a new user playlist.

        :param str playlist_title: playlist title
        :param callback: function to perform once, the playlist is created
        """
        if self._tracker_playlists is None:
            return

        self._tracker_playlists.create_playlist(playlist_title, callback)
