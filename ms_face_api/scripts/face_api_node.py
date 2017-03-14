#!/usr/bin/env python
from ms_face_api import Key, face as CF, person_group as PG
from ms_face_api.util import CognitiveFaceException

import rospy
from cv_bridge import CvBridge
from cv2 import startWindowThread, imencode, imread
from StringIO import StringIO
from sensor_msgs.msg import Image
from ms_face_api.srv import PersonGroupSelect, Detect
from ms_face_api.msg import Face, Faces
from json import dumps
from math import pi


class CognitiveFaceROS:

    def __init__(self):
        self._api_key = rospy.get_param('~key',
                                        'be062e88698e4777ac6196623d7230dd')
        self._topic_timeout = rospy.get_param('~timeout', 10)
        self._cv_bridge = CvBridge()
        startWindowThread()
        Key.set(self._api_key)
        self._srv_person_group_select = rospy.Service('~person_group_select',
                                                      PersonGroupSelect,
                                                      self._person_group_select
                                                      )
        self._srv_detect = rospy.Service('~detect',
                                         Detect,
                                         self._detect_srv
                                         )

        self._person_group_id = rospy.get_param('~person_group',
                                                'default_group')
        self._init_person_group(self._person_group_id)

    def _init_person_group(self, gid, delete_first=False):
        person_group = None
        try:
            person_group = PG.get(gid)
            rospy.loginfo('getting person group "%s"'
                          % person_group)
        except CognitiveFaceException as e:
            rospy.loginfo('person group "%s" doesn\'t exist, needs creating.'
                          ' Exception: %s'
                          % (gid, e))
        try:
            # if we are expected to reinitialise this, and the group
            # already existed, delete it first
            if person_group is not None and delete_first:
                rospy.loginfo('delete existing person group "%s"'
                              ' before re-creating it.' % gid)
                PG.delete(gid)
                person_group = None
            # if the group does not exist, we gotto create it
            if person_group is None:
                rospy.loginfo('creating new person group "%s".'
                              % gid)
                PG.create(gid, user_data=dumps({
                    'created_by': rospy.get_name()
                }))
            rospy.loginfo('active person group is now "%s".' % gid)
            self._person_group_id = gid
            print PG.lists()
        except CognitiveFaceException as e:
            rospy.logwarn('Operation failed for person group "%s".'
                          ' Exception: %s'
                          % (gid, e))

    def _convert_ros2jpg(self, image_msg):
        img = self._cv_bridge.imgmsg_to_cv2(image_msg, "bgr8")
        retval, buf = imencode('.jpg', img)
        return buf.tostring()

    def _person_group_select(self, req):
        print req
        self._init_person_group(req.id, req.delete_group)
        return []

    def _get_image(self, req):
        if req.filename is not '':
            img = imread(req.filename)
            msg = self._cv_bridge.cv2_to_imgmsg(img, 'bgr8')
        elif req.topic is not '':
            try:
                msg = rospy.wait_for_message(req.topic, Image,
                                             timeout=self._topic_timeout)
            except rospy.ROSException as e:
                rospy.logwarn('could not receive image from topic %s'
                              ' within %f seconds: %s' %
                              (req.topic, self._topic_timeout, e.message))
                return Faces()
        else:
            msg = req.image
        return msg

    def _detect_srv(self, req):
        return self._detect(self._get_image(req), req.identify)

    def _detect(self, image, identify=False):
        faces = Faces()
        try:
            data = CF.detect(
                StringIO(self._convert_ros2jpg(image)),
                landmarks=True,
                attributes='age,gender,headPose,smile,glasses')
            identities = {}
            if identify:
                ids = [f['faceId'] for f in data]
                try:
                    identified = CF.identify(ids[0:10], self._person_group_id)
                    print identified
                except CognitiveFaceException as e:
                    rospy.logwarn('identification did not work: %s' %
                                  str(e))
            for f in data:
                face = Face()
                face.faceId = f['faceId']
                if face.faceId in identities:
                    face.person = identities[face.faceId]
                else:
                    face.person = ''
                face.faceRectangle.x_offset = f['faceRectangle']['left']
                face.faceRectangle.y_offset = f['faceRectangle']['top']
                face.faceRectangle.width = f['faceRectangle']['width']
                face.faceRectangle.height = f['faceRectangle']['height']
                face.faceRectangle.do_rectify = False
                face.faceLandmarks = dumps(f['faceLandmarks'])
                face.gender = f['faceAttributes']['gender']
                face.age = f['faceAttributes']['age']
                face.smile = f['faceAttributes']['smile']
                face.rpy.x = (f['faceAttributes']['headPose']['roll'] /
                              180.0 * pi)
                face.rpy.y = (f['faceAttributes']['headPose']['pitch'] /
                              180.0 * pi)
                face.rpy.z = (f['faceAttributes']['headPose']['yaw'] /
                              180.0 * pi)
                faces.faces.append(face)
            faces.header = image.header
        except Exception as e:
            rospy.logwarn('failed to detect via the MS Face API: %s' %
                          str(e))
        return faces


rospy.init_node('cogntivefaceapi')
cfa = CognitiveFaceROS()
#msg = rospy.wait_for_message('/image', Image)
#print cfa._detect(msg)
rospy.spin()
