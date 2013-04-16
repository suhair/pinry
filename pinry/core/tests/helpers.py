from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.files.images import ImageFile
from django.db.models.signals import post_save
from django.db.models.query import QuerySet
from django.test import TestCase
from django_images.models import Thumbnail

import factory
from django_images.models import original_changed
from taggit.models import Tag

from ..models import Pin, Image
from ...users.models import User


LOGO_PATH = 'logo.png'


class UserFactory(factory.DjangoModelFactory):
    FACTORY_FOR = User

    username = factory.Sequence(lambda n: 'user_{}'.format(n))
    email = factory.Sequence(lambda n: 'user_{}@example.com'.format(n))
    password = factory.PostGenerationMethodCall('set_password', 'password')

    @factory.post_generation
    def user_permissions(self, create, extracted, **kwargs):
        perm_codenames = ['add_pin', 'add_image']
        permissions = Permission.objects.filter(codename__in=perm_codenames)
        self.user_permissions = permissions


class TagFactory(factory.DjangoModelFactory):
    FACTORY_FOR = Tag

    name = factory.Sequence(lambda n: 'tag_{}'.format(n))


class ImageFactory(factory.DjangoModelFactory):
    FACTORY_FOR = Image

    image = factory.LazyAttribute(lambda a: ImageFile(open(LOGO_PATH, 'rb')))

    @factory.post_generation
    def create_thumbnails(self, create, extracted, **kwargs):
        for size in settings.IMAGE_SIZES.keys():
            Thumbnail.objects.get_or_create_at_size(self.pk, size)

    @classmethod
    def create(cls, **kwargs):
        """
        Create a new instance of the Image model

        Disconnect the original_changed receiver from the post_save signal
        in order to avoid deleting thumbnail objects that are being generated
        in create_thumbnails() method. Factory Boy saves object after
        all post generation hooks are called, which emits the post_save
        signal for it.
        """
        post_save.disconnect(original_changed)
        image = super(ImageFactory, cls).create(**kwargs)
        post_save.connect(receiver=original_changed)
        return image


class PinFactory(factory.DjangoModelFactory):
    FACTORY_FOR = Pin

    submitter = factory.SubFactory(UserFactory)
    image = factory.SubFactory(ImageFactory)

    @factory.post_generation
    def tags(self, create, extracted, **kwargs):
        if isinstance(extracted, Tag):
            self.tags.add(extracted)
        elif isinstance(extracted, list):
            self.tags.add(*extracted)
        elif isinstance(extracted, QuerySet):
            self.tags = extracted
        else:
            self.tags.add(TagFactory())


class PinFactoryTest(TestCase):
    def test_default_tags(self):
        self.assertTrue(PinFactory().tags.get(pk=1).name.startswith('tag_'))

    def test_custom_tag(self):
        custom = 'custom_tag'
        pin = PinFactory(tags=Tag.objects.create(name=custom))
        self.assertEqual(pin.tags.get(pk=1).name, custom)

    def test_custom_tags_list(self):
        tags = TagFactory.create_batch(2)
        PinFactory(tags=tags)
        self.assertEqual(Tag.objects.count(), 2)

    def test_custom_tags_queryset(self):
        TagFactory.create_batch(2)
        tags = Tag.objects.all()
        PinFactory(tags=tags)
        self.assertEqual(Tag.objects.count(), 2)

    def test_empty_tags(self):
        PinFactory(tags=[])
        self.assertEqual(Tag.objects.count(), 0)
