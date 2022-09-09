# aboutwindow.py
#
# Copyright 2022 Christopher Davis <christopherdavis@gnome.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-2.0-or-later

from gettext import gettext as _

from gi.repository import Adw, Gtk


def show_about(app_id, version, parent):
    developers = [
        "Abhinav Singh",
        "Adam Blanchet",
        "Adrian Solom",
        "Alberto Fanjul",
        "Alexander Mikhaylenko",
        "Andre Klapper",
        "Andreas Nilsson",
        "Apostol Bakalov",
        "Arnel A. Borja",
        "Ashwani Singh Tanwar",
        "Ashwin Mohan",
        "Atharva Veer",
        "Benoît Legat",
        "Bilal Elmoussaoui",
        "Billy Barrow",
        "Bruce Cowan",
        "Carlos Garnacho",
        "Carlos Soriano",
        "Chinmay Gurjar",
        "Christophe van den Abbeele",
        "Christopher Davis",
        "Clayton G. Hobbs",
        "Divyanshu Vishwakarma",
        "Eslam Mostafa",
        "Elias Entrup",
        "Erik Inkinen",
        "Evan Nehring",
        "Evandro Giovanini",
        "Fabiano Fidêncio",
        "Felipe Borges",
        "Florian Darfeuille",
        "Gaurav Narula",
        "Georges Basile Stavracas Neto",
        "Guillaume Quintard",
        "Gyanesh Malhotra",
        "Harry Xie",
        "Hugo Posnic",
        "Ishaan Shah",
        "Islam Bahnasy",
        "Jakub Steiner",
        "James A. Baker",
        "Jan Alexander Steffens",
        "Janne Körkkö",
        "Jan-Michael Brummer",
        "Jean Felder",
        "Jeremy Bicha",
        "Jesus Bermudez Velazquez",
        "Jordan Petridis",
        "Juan José González",
        "Juan Suarez",
        "Kainaat Singh",
        "Kalev Lember",
        "Kevin Haller",
        "Konstantin Pospelov",
        "Koushik Sahu",
        "Lucy Coleclough",
        "Marinus Schraal",
        "Michael Catanzaro",
        "Mohanna Datta Yelugoti",
        "Nick Richards",
        "Niels De Graef",
        "Nikolay Yanchuk",
        "Nils Reuße",
        "Pablo Palácios",
        "Phil Dawson",
        "Piotr Drąg",
        "Prashant Tyagi",
        "Rafael Coelho",
        "Rashi Sah",
        "Rasmus Thomsen",
        "Reuben Dsouza",
        "Robert Greener",
        "Sabri Ünal",
        "Sagar Lakhani",
        "Sai Suman Prayaga",
        "Sam Hewitt",
        "Sam Thursfield",
        "Sambhav Kothari",
        "Seif Lotfy",
        "Shivani Poddar",
        "Shivansh Handa",
        "Simon McVittie",
        "Sophie Herold",
        "Subhadip Jana",
        "Sumaid Syed",
        "Suyash Garg",
        "Tapasweni Pathak",
        "Taylor Garcia",
        "Tjipke van der Heide",
        "Vadim Rutkovsky",
        "Veerasamy Sevagen",
        "Vineet Reddy",
        "Weifang Lai",
        "Yann Delaby",
        "Yash Singh",
        "Yosef Or Boczko"
    ]

    designers = [
        "Allan Day",
        "Jakub Steiner",
        "William Jon McCann"
    ]

    translators = [
        "Adolfo Jayme Barrientos",
        "அருள்ராஜன் அ லை",
        "A S Alam",
        "Alain Lojewski",
        "Alan Mortensen",
        "Aleksandr Melman",
        "Alexander Shopov",
        "Alexandre Franke",
        "Alexey Rubtsov",
        "Anders Jonsson",
        "Andika Triwidada",
        "Anish Sheela",
        "Arash Mousavi",
        "Asier Sarasua Garmendia",
        "Ask Hjorth Larsen",
        "Aurimas Černius",
        "Balázs Meskó",
        "Balázs Úr",
        "Baurzhan Muftakhidinov",
        "Bruce Cowan",
        "Boyuan Yang",
        "Carmen Bianca Bakker",
        "Cédric Valmary",
        "Chao-Hsiung Liao",
        "Charles Monzat",
        "Cheng Lu",
        "Cheng-Chia Tseng",
        "Claude Paroz",
        "Danial Behzadi",
        "Daniel Korostil",
        "Daniel Mustieles García",
        "Daniel Șerbănescu",
        "David King",
        "Dušan Kazik",
        "Efstathios Iosifidis",
        "Emin Tufan Çetin",
        "Enrico Nicoletto",
        "Fábio Nogueira",
        "Fabio Tomat",
        "Florentina Mușat",
        "Fran Diéguez",
        "Furkan Tokaç",
        "Gábor Kelemen",
        "Gil Forcada Codinachs",
        "Goran Vidović",
        "Guillaume Bernard",
        "Henrique Machado Campos",
        "Hugo Carvalho",
        "Inaki Larranaga Murgoitio",
        "Jiri Grönroos",
        "Joe Hansen",
        "Jor Teron",
        "Jordi Mas",
        "Juliano Camargo",
        "Julien Humbert",
        "Justin van Steijn",
        "Kjartan Maraas",
        "Kristjan Schmidt",
        "Kukuh Syafaat",
        "Luna Jernberg",
        "Марко Костић",
        "Marek Černocký",
        "Mario Blättermann",
        "Matej Urbančič",
        "Matheus Barbosa",
        "Milo Casagrande",
        "Mingcong Bai",
        "Mpho Jele",
        "Мирослав Николић",
        "Милош Поповић",
        "Nathan Follens",
        "Osman Karagöz",
        "Petr Kovář",
        "Philipp Kiemle",
        "Piotr Drąg",
        "Quentin Pagès",
        "Rafael Fontenelle",
        "Rodrigo Lledó Milanca",
        "Rūdolfs Mazurs",
        "Ryuta Fujii",
        "Rūdolfs Mazurs",
        "Sabri Ünal",
        "Sebastian Rasmussen",
        "Seong-ho Cho",
        "Stas Solovey",
        "Sveinn í Felli",
        "Tiago Santos",
        "Tim Sabsch",
        "Tjipke van der Heide",
        "Tom Tryfonidis",
        "Trần Ngọc Quân",
        "Vinzenz Vietzke",
        "Xavi Ivars",
        "Yaron Shahrabani",
        "Yi-Jyun Pan",
        "Yosef Or Boczko",
        "Yuras Shumovich",
        "Yuri Chornoivan",
        "Yuri Myasoedov",
        "Zander Brown",
        "Zmicer Turok",
    ]

    about = Adw.AboutWindow(
        application_name=_("Music"),
        application_icon=app_id,
        developer_name=_("The GNOME Project"),
        transient_for=parent,
        developers=developers,
        designers=designers,
        translator_credits=_("translator-credits"),
        version=version,
        website="https://wiki.gnome.org/Apps/Music",
        issue_url="https://gitlab.gnome.org/GNOME/gnome-music/-/issues/new",
        copyright=_("Copyright The GNOME Music Developers"),
        license_type=Gtk.License.GPL_2_0)

    about.add_credit_section(_("Translated by"), translators)

    about.present()