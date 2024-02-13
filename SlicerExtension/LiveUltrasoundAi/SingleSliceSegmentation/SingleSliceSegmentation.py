from __future__ import print_function
import os
import vtk, qt, ctk, slicer
import logging
import numpy as np

from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin



DEFAULT_INPUT_IMAGE_NAME = "Image_Image"

#
# SingleSliceSegmentation
#

class SingleSliceSegmentation(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Single Slice Segmentation"
    self.parent.categories = ["Ultrasound"]
    self.parent.dependencies = []
    self.parent.contributors = ["Tamas Ungi (Queen's University)"] # replace with "Firstname Lastname (Organization)"
    self.parent.helpText = """
This is an example of scripted loadable module bundled in an extension.
It performs a simple thresholding on the input volume and optionally captures a screenshot.
"""
    self.parent.helpText += self.getDefaultModuleDocumentationLink()
    self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc.
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""" # replace with organization, grant and thanks.


    def setup(self):
      # Register subject hierarchy plugin
      import SubjectHierarchyPlugins
      scriptedPlugin = slicer.qSlicerSubjectHierarchyScriptedPlugin(None)
      scriptedPlugin.setPythonSource(SubjectHierarchyPlugins.SegmentEditorSubjectHierarchyPlugin.filePath)

#
# SingleSliceSegmentationWidget
#

class SingleSliceSegmentationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """
  ATTRIBUTE_PREFIX = 'SingleSliceSegmentation_'
  EXPORT_FOLDER = ATTRIBUTE_PREFIX + 'FilenamePrefix'
  INPUT_BROWSER = ATTRIBUTE_PREFIX + 'InputBrowser'
  INPUT_SKIP_NUMBER = ATTRIBUTE_PREFIX + 'InputSkipNumber'
  DEFAULT_INPUT_SKIP_NUMBER = 4
  INPUT_LAST_INDEX = ATTRIBUTE_PREFIX + 'InputLastIndex'
  INPUT_IMAGE_ID = ATTRIBUTE_PREFIX + 'InputImageId'
  SEGMENTATION = ATTRIBUTE_PREFIX + 'Segmentation'
  OUTPUT_BROWSER = ATTRIBUTE_PREFIX + 'OutputBrowser'
  ORIGINAL_IMAGE_INDEX = ATTRIBUTE_PREFIX + 'OriginalImageIndex'


  def __init__(self, parent):
    ScriptedLoadableModuleWidget.__init__(self, parent)
    VTKObservationMixin.__init__(self)

    self.logic = SingleSliceSegmentationLogic()

    # Members

    self.parameterSetNode = None
    self.editor = None
    self.ui = None
    self.lastForegroundOpacity = 0.3  # Default value for CT/MRI overlay
    
    # Shortcuts

    self.shortcutS = qt.QShortcut(slicer.util.mainWindow())
    self.shortcutS.setKey(qt.QKeySequence('s'))
    self.shortcutD = qt.QShortcut(slicer.util.mainWindow())
    self.shortcutD.setKey(qt.QKeySequence('d'))
    self.shortcutC = qt.QShortcut(slicer.util.mainWindow())
    self.shortcutC.setKey(qt.QKeySequence('c'))
    self.shortcutA = qt.QShortcut(slicer.util.mainWindow())
    self.shortcutA.setKey(qt.QKeySequence('a'))

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer)

    uiWidget = slicer.util.loadUI(self.resourcePath('UI/SingleSliceSegmentation.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set up widgets

    self.ui.inputSequenceBrowserSelector.setMRMLScene(slicer.mrmlScene)
    self.ui.inputVolumeSelector.setMRMLScene(slicer.mrmlScene)
    self.ui.inputSegmentationSelector.setMRMLScene(slicer.mrmlScene)
    self.ui.segmentationBrowserSelector.setMRMLScene(slicer.mrmlScene)

    # connections

    # Observe scene end import event and call onSceneEndImport when it happens
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndImportEvent, self.onSceneEndImport)

    self.ui.inputSequenceBrowserSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onInputBrowserChanged)
    self.ui.inputVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onInputVolumeChanged)
    self.ui.inputSegmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSegmentationChanged)
    self.ui.segmentationBrowserSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSegmentationBrowserChanged)
    self.ui.skipImagesSpinBox.connect("valueChanged(int)", self.onSkipImagesNumChanged)

    self.ui.captureButton.connect('clicked(bool)', self.onCaptureButton)
    self.ui.clearSegmentationButton.connect('clicked(bool)', self.onClearButton)
    self.ui.skipImageButton.connect('clicked(bool)', self.onSkipButton)

    self.ui.outputDirectoryButton.connect('directoryChanged(QString)', self.onExportFolderChanged)
    self.ui.convertSegButton.connect('clicked(bool)', self.onConvertButton)
    self.ui.exportButton.connect('clicked(bool)', self.onExportButton)
    self.ui.layoutSelectButton.connect('clicked(bool)', self.onLayoutSelectButton)
    self.ui.overlayButton.connect('clicked(bool)', self.onOverlayClicked)

    self.ui.editor.setMRMLScene(slicer.mrmlScene)
    
    import qSlicerSegmentationsEditorEffectsPythonQt
    # TODO: For some reason the instance() function cannot be called as a class function although it's static
    factory = qSlicerSegmentationsEditorEffectsPythonQt.qSlicerSegmentEditorEffectFactory()
    self.effectFactorySingleton = factory.instance()
    self.effectFactorySingleton.connect('effectRegistered(QString)', self.editorEffectRegistered)

    # Add custom layout to layout selection menu
    customLayout = """
    <layout type="horizontal" split="true">
      <item>
       <view class="vtkMRMLSliceNode" singletontag="Red">
        <property name="orientation" action="default">Axial</property>
        <property name="viewlabel" action="default">R</property>
        <property name="viewcolor" action="default">#F34A33</property>
       </view>
      </item>
      <item>
       <view class="vtkMRMLViewNode" singletontag="1">
         <property name="viewlabel" action="default">1</property>
       </view>
      </item>
    </layout>
    """

    customLayoutId = 501

    layoutManager = slicer.app.layoutManager()
    layoutManager.layoutLogic().GetLayoutNode().AddLayoutDescription(customLayoutId, customLayout)

    viewToolBar = slicer.util.mainWindow().findChild('QToolBar', 'ViewToolBar')
    layoutMenu = viewToolBar.widgetForAction(viewToolBar.actions()[0]).menu()
    layoutSwitchActionParent = layoutMenu
    layoutSwitchAction = layoutSwitchActionParent.addAction("red + 3D side by side")  # add inside layout list
    layoutSwitchAction.setData(customLayoutId)
    # layoutSwitchAction.setIcon(qt.QIcon(':Icons/Go.png'))
    layoutSwitchAction.setToolTip('3D and slice view')
    layoutSwitchAction.connect('triggered()', lambda layoutId=customLayoutId: slicer.app.layoutManager().setLayout(layoutId))

    customLayout = """
    <layout type="horizontal" split="true">
      <item>
       <view class="vtkMRMLSliceNode" singletontag="Red">
        <property name="orientation" action="default">Axial</property>
        <property name="viewlabel" action="default">R</property>
        <property name="viewcolor" action="default">#F34A33</property>
       </view>
      </item>
      <item>
        <layout type=\"horizontal\">
          <item>
            <view class="vtkMRMLViewNode" singletontag="1">
              <property name="viewlabel" action="default">1</property>
            </view>
          </item>
          <item>
            <view class="vtkMRMLViewNode" singletontag="2" type="secondary">
              <property name="viewlabel" action="default">2</property>
            </view>
          </item>
        </layout>
      </item>
    </layout>
    """

    customLayoutId = 502

    layoutManager.layoutLogic().GetLayoutNode().AddLayoutDescription(customLayoutId, customLayout)

    layoutSwitchActionParent = layoutMenu
    layoutSwitchAction = layoutSwitchActionParent.addAction("red + stacked dual 3D")  # add inside layout list
    layoutSwitchAction.setData(customLayoutId)
    # layoutSwitchAction.setIcon(qt.QIcon(':Icons/Go.png'))
    layoutSwitchAction.setToolTip('Dual 3D and slice view')
    layoutSwitchAction.connect('triggered()',
                               lambda layoutId=customLayoutId: slicer.app.layoutManager().setLayout(layoutId))

  def cleanup(self):
    self.effectFactorySingleton.disconnect('effectRegistered(QString)', self.editorEffectRegistered)

  def onExportFolderChanged(self, text):
    """Save the filename prefix in application settings"""
    settings = qt.QSettings()
    settings.setValue(self.EXPORT_FOLDER, text)

  def onInputBrowserChanged(self, currentNode):
    browserNodes = slicer.util.getNodesByClass('vtkMRMLSequenceBrowserNode')
    for browser in browserNodes:
      browser.SetAttribute(self.INPUT_BROWSER, "False")

    if currentNode is None:
      return

    currentNode.SetAttribute(self.INPUT_BROWSER, "True")
    
    savedSkip = currentNode.GetAttribute(self.INPUT_SKIP_NUMBER)
    if savedSkip is not None:
      slicer.modules.singleslicesegmentation.widgetRepresentation().self().ui.skipImagesSpinBox.value = int(savedSkip)
    else:
      numSkip = slicer.modules.singleslicesegmentation.widgetRepresentation().self().ui.skipImagesSpinBox.value
      currentNode.SetAttribute(self.INPUT_SKIP_NUMBER, str(numSkip))
    
    logging.debug("onSequenceBrowserSelected: {}".format(currentNode.GetName()))

  def onInputVolumeChanged(self, currentNode):
    # todo: delete after testing parameter node
    # volumeNodes = slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
    # for volume in volumeNodes:
    #   volume.SetAttribute(self.INPUT_IMAGE, "False")

    if currentNode is None:
      self.parameterSetNode.RemoveAttribute(self.INPUT_IMAGE_ID)
    else:
      self.parameterSetNode.SetAttribute(self.INPUT_IMAGE_ID, currentNode.GetID())

  def onSegmentationChanged(self, currentNode):
    segmentationNodes = slicer.util.getNodesByClass('vtkMRMLSegmentationNode')
    for segmentation in segmentationNodes:
      segmentation.SetAttribute(self.SEGMENTATION, "False")

    if currentNode is None:
      return
    else:
      currentNode.SetAttribute(self.SEGMENTATION, "True")


  def onSegmentationBrowserChanged(self, currentNode):
    browserNodes = slicer.util.getNodesByClass('vtkMRMLSequenceBrowserNode')
    for browser in browserNodes:
      browser.SetAttribute(self.OUTPUT_BROWSER, "False")

    if currentNode is None:
      return
    else:
      currentNode.SetAttribute(self.OUTPUT_BROWSER, "True")

  def onImageChange(self, browserNode):
    inputImageIndex = browserNode.GetSelectedItemNumber()

    if inputImageIndex is not None:
      inputBrowserNode.SetAttribute(self.ORIGINAL_IMAGE_INDEX, str(inputImageIndex))
  
  def onSkipImagesNumChanged(self, value):
    inputBrowserNode = self.ui.inputSequenceBrowserSelector.currentNode()
    if inputBrowserNode is not None:
      inputBrowserNode.SetAttribute(self.INPUT_SKIP_NUMBER, str(value))
  
  def onCaptureButton(self):
    """
    Callback function for capture button or hotkey to trigger either saving of a new segmentation (if the input image sequence
    browser is selected) or overwriting an existing segmentation (if the segmentation sequence is selected).
    :returns: None
    """
    inputBrowserNode = self.ui.inputSequenceBrowserSelector.currentNode()
    inputImage = self.ui.inputVolumeSelector.currentNode()
    outputBrowserNode = self.ui.segmentationBrowserSelector.currentNode()
    selectedSegmentation = self.ui.inputSegmentationSelector.currentNode()
    numSkip = slicer.modules.singleslicesegmentation.widgetRepresentation().self().ui.skipImagesSpinBox.value

    if inputBrowserNode is None:
      logging.error("No browser node selected!")
      return
    if selectedSegmentation is None:
      logging.error("No segmentation selected!")
      return
    if outputBrowserNode is None:
      logging.error("No segmentation sequence browser selected!")
      return

    original_index_str = selectedSegmentation.GetAttribute(self.ORIGINAL_IMAGE_INDEX)

    # If input sequence browser is selected in the toolbar, always consider this a new segmentation. This is needed in case
    # a scene was loaded with segmentation attribute ORIGINAL_IMAGE_INDEX not None.

    activeBrowserNode = slicer.modules.sequences.toolBar().activeBrowserNode()
    if activeBrowserNode == inputBrowserNode:
      original_index_str = None

    if original_index_str is None or original_index_str == "None" or original_index_str == "":  # new segmentation
      inputImageIndex = inputBrowserNode.GetSelectedItemNumber()
      selectedSegmentation.SetAttribute(self.ORIGINAL_IMAGE_INDEX, str(inputImageIndex))
      self.logic.captureSlice(outputBrowserNode, selectedSegmentation, inputImage)
      self.logic.eraseCurrentSegmentation(selectedSegmentation)
      selectedSegmentation.SetAttribute(self.ORIGINAL_IMAGE_INDEX, "None")
      currentItemNum = inputBrowserNode.GetSelectedItemNumber()
      newItemNum = inputBrowserNode.SelectNextItem(numSkip)
    else:  # overwrite segmentation
      self.logic.captureSlice(outputBrowserNode, selectedSegmentation, inputImage)
      currentItemNum = outputBrowserNode.GetSelectedItemNumber()
      newItemNum = outputBrowserNode.SelectNextItem()

    # Check if sequence browser wrapped around. If yes, pop up message box to ask if user wants to continue.

    if newItemNum < currentItemNum:
      logging.debug("Sequence wrapped around!")

      msgBox = qt.QMessageBox()
      msgBox.setText("Sequence wrapped around!")
      msgBox.setInformativeText("Please save the scene before closing the application!")
      msgBox.setStandardButtons(qt.QMessageBox.Ok)
      msgBox.setDefaultButton(qt.QMessageBox.Ok)
      msgBox.exec_()

  def onClearButton(self):
    """
    Callback function for "delete" button. Clears segmentation canvas.
    :returns: none
    """
    selectedSegmentation = self.ui.inputSegmentationSelector.currentNode()
    if selectedSegmentation is None:
      logging.error("No segmentation selected!")
      return
    self.logic.eraseCurrentSegmentation(selectedSegmentation)
  
  def onSkipButton(self):
    """
    Callback function for skip button or hotkey. If input sequence browser is active, skips specified number of frames without
    recording any segmentation. If output sequence browser is active, moves to the next output frame without skipping any frames
    because the user is probably editing/overwriting existing segmentations.
    :returns: None
    """
    inputBrowserNode = self.ui.inputSequenceBrowserSelector.currentNode()
    selectedSegmentation = self.ui.inputSegmentationSelector.currentNode()
    outputBrowserNode = self.ui.segmentationBrowserSelector.currentNode()

    numSkip = slicer.modules.singleslicesegmentation.widgetRepresentation().self().ui.skipImagesSpinBox.value
    if inputBrowserNode is None:
      logging.error("No browser node selected!")
      return
    if selectedSegmentation is None:
      logging.error("No segmentation selected!")
      return

    activeBrowserNode = slicer.modules.sequences.toolBar().activeBrowserNode()
    if activeBrowserNode == outputBrowserNode:
      currentItemNum = outputBrowserNode.GetSelectedItemNumber()
      newItemNum = outputBrowserNode.SelectNextItem()
    else:
      self.logic.eraseCurrentSegmentation(selectedSegmentation)
      currentItemNum = inputBrowserNode.GetSelectedItemNumber()
      newItemNum = inputBrowserNode.SelectNextItem(numSkip)

    # Check if sequence browser wrapped around. If yes, pop up message box to ask if user wants to continue.

    if newItemNum < currentItemNum:
      logging.debug("Sequence wrapped around!")
      msgBox = qt.QMessageBox()
      msgBox.setText("Sequence wrapped around!")
      msgBox.setInformativeText("Please save the scene before closing the application!")
      msgBox.setStandardButtons(qt.QMessageBox.Ok)
      msgBox.setDefaultButton(qt.QMessageBox.Ok)
      msgBox.exec_()

  def onConvertButton(self):
    """
    Callback function for convert button.
    Converts all segmentations in the segmentation sequence browser to a sequence of scalar volumes.
    """
    inputBrowserNode = self.ui.segmentationBrowserSelector.currentNode()
    if inputBrowserNode is None:
      logging.error("No browser node selected!")
      return

    segmentationNode = self.ui.inputSegmentationSelector.currentNode()
    if segmentationNode is None:
      logging.error("No segmentation selected!")
      return

    ultrasoundNode = self.ui.inputVolumeSelector.currentNode()
    if ultrasoundNode is None:
      logging.error("No ultrasound volume selected!")
      return

    value = self.ui.convertValueSpinBox.value

    self.logic.convertSegmentationSequenceToVolumeSequence(inputBrowserNode, segmentationNode, ultrasoundNode, value)

  def onExportButton(self):
    selectedSegmentationSequence = self.ui.segmentationBrowserSelector.currentNode()
    selectedSegmentation = self.ui.inputSegmentationSelector.currentNode()
    selectedImage = self.ui.inputVolumeSelector.currentNode()
    selectedImageSequence = self.ui.inputSequenceBrowserSelector.currentNode()
    outputFolder = self.ui.outputDirectoryButton.directory
    baseName = self.ui.filenamePrefixEdit.text

    if selectedSegmentation is None:
      logging.error("No segmentation selected!")
      return
    if selectedSegmentationSequence is None:
      logging.error("No segmentation sequence browser selected!")
      return
    if selectedImage is None:
      logging.error("No image selected!")
      return
    if selectedImage is None:
      logging.error("No image sequence browser selected!")
      return

    if self.ui.exportTransformCheckBox.checked:
      self.logic.exportNumpySlice(selectedImage,
                                  selectedImageSequence,
                                  selectedSegmentation,
                                  selectedSegmentationSequence,
                                  outputFolder,
                                  baseName)
      self.logic.exportTransformToWorldSequence(selectedImage,
                                                selectedImageSequence,
                                                selectedSegmentation,
                                                selectedSegmentationSequence,
                                                outputFolder,
                                                baseName)
    else:
      self.logic.exportPngSequence(selectedImage,
                                 selectedImageSequence,
                                 selectedSegmentation,
                                 selectedSegmentationSequence,
                                 outputFolder,
                                 baseName)

  def onLayoutSelectButton(self):
    layoutManager = slicer.app.layoutManager()
    currentLayout = layoutManager.layout

    # place skeleton model in first 3d view
    skeleton_volume = slicer.util.getFirstNodeByName("SkeletonModel")
    viewNode = layoutManager.threeDWidget(0).mrmlViewNode()

    if skeleton_volume is not None:
      displayNode = skeleton_volume.GetDisplayNode()
      displayNode.SetViewNodeIDs([viewNode.GetID()])

    # place reconstructed volume in second 3d view

    # hacky but necessary way to ensure that we grab the correct browser node
    i = 1
    found = False
    browser = slicer.util.getFirstNodeByClassByName('vtkMRMLSequenceBrowserNode', 'LandmarkingScan')
    while not found and i < 6:
      if browser == None:
        browser = slicer.util.getFirstNodeByClassByName('vtkMRMLSequenceBrowserNode', 'LandmarkingScan_{}'.format(str(i)))
        if browser != None:
          found = True
      else:
        found = True

      i += 1

    if browser is not None:
      spine_volume = slicer.util.getFirstNodeByName(browser.GetName() + 'ReconstructionResults')
      if layoutManager.threeDWidget(1) is not None:
        viewNode = layoutManager.threeDWidget(1).mrmlViewNode()
      else:
        newView = slicer.vtkMRMLViewNode()
        newView = slicer.mrmlScene.AddNode(newView)
        newWidget = slicer.qMRMLThreeDWidget()
        newWidget.setMRMLScene(slicer.mrmlScene)
        newWidget.setMRMLViewNode(newView)

      if spine_volume is not None:
        displayNode = slicer.modules.volumerendering.logic().GetFirstVolumeRenderingDisplayNode(spine_volume)
        displayNode.SetViewNodeIDs([viewNode.GetID()])
        spine_volume.SetDisplayVisibility(1)


    if currentLayout == 501:
      layoutManager.setLayout(502) # switch to dual 3d + red slice layout
    elif currentLayout == 502:
      layoutManager.setLayout(6) # switch to red slice only layout
    else:
      layoutManager.setLayout(501) # switch to custom layout with 3d viewer

  def onOverlayClicked(self):
    # show/hide foreground image

    layoutManager = slicer.app.layoutManager()
    compositeNode = layoutManager.sliceWidget('Red').sliceLogic().GetSliceCompositeNode()
    currentOpacity = compositeNode.GetForegroundOpacity()
    if currentOpacity == 0:
      compositeNode.SetForegroundOpacity(self.lastForegroundOpacity)
    else:
      self.lastForegroundOpacity = currentOpacity
      compositeNode.SetForegroundOpacity(0.0)

  # Segment Editor Functionalities

  def editorEffectRegistered(self):
    self.editor.updateEffectList()

  def selectParameterNode(self):
    # Select parameter set node if one is found in the scene, and create one otherwise
    segmentEditorSingletonTag = "SegmentEditor"
    segmentEditorNode = slicer.mrmlScene.GetSingletonNode(segmentEditorSingletonTag, "vtkMRMLSegmentEditorNode")
    if segmentEditorNode is None:
      segmentEditorNode = slicer.vtkMRMLSegmentEditorNode()
      segmentEditorNode.SetSingletonTag(segmentEditorSingletonTag)
      segmentEditorNode = slicer.mrmlScene.AddNode(segmentEditorNode)
    if self.parameterSetNode == segmentEditorNode:
      # nothing changed
      return
    self.parameterSetNode = segmentEditorNode
    self.ui.editor.setMRMLSegmentEditorNode(self.parameterSetNode)

  def getCompositeNode(self, layoutName):
    """ use the Red slice composite node to define the active volumes """
    count = slicer.mrmlScene.GetNumberOfNodesByClass('vtkMRMLSliceCompositeNode')

    for n in range(count):
      compNode = slicer.mrmlScene.GetNthNodeByClass(n, 'vtkMRMLSliceCompositeNode')
      if layoutName and compNode.GetLayoutName() != layoutName:
        continue
      return compNode

  def getDefaultMasterVolumeNodeID(self):
    layoutManager = slicer.app.layoutManager()
    # Use first background volume node in any of the displayed layouts
    for layoutName in layoutManager.sliceViewNames():
      compositeNode = self.getCompositeNode(layoutName)
      if compositeNode.GetBackgroundVolumeID():
        return compositeNode.GetBackgroundVolumeID()
    # Use first background volume node in any of the displayed layouts
    for layoutName in layoutManager.sliceViewNames():
      compositeNode = self.getCompositeNode(layoutName)
      if compositeNode.GetForegroundVolumeID():
        return compositeNode.GetForegroundVolumeID()
    # Not found anything
    return None

  def enter(self):
    """Runs whenever the module is reopened"""
    logging.debug('Entered SingleSliceSegmentation module widget')

    # Prevent segmentation master volume to be created in the wrong position.
    # Todo: Instead of this, the input image should be kept transformed, and the segmentation also transformed

    # inputImageNode = slicer.util.getFirstNodeByName(DEFAULT_INPUT_IMAGE_NAME)

    # if inputImageNode is not None and inputImageNode.GetClassName() == 'vtkMRMLScalarVolumeNode':
    #   inputImageNode.SetAndObserveTransformNodeID(None)

    if self.ui.editor.turnOffLightboxes():
      slicer.util.warningDisplay('Segment Editor is not compatible with slice viewers in light box mode.'
                                 'Views are being reset.', windowTitle='Segment Editor')

    # Allow switching between effects and selected segment using keyboard shortcuts
    self.ui.editor.installKeyboardShortcuts()

    # Set parameter set node if absent
    self.selectParameterNode()
    self.ui.editor.updateWidgetFromMRML()
    
    # Update UI
    slicer.modules.sequences.setToolBarVisible(True)
    self.updateSelections()
    self.connectKeyboardShortcuts()

    # Collapse input group if all is selected

    if self.ui.inputSequenceBrowserSelector.currentNode() is not None and\
      self.ui.inputVolumeSelector.currentNode() is not None and\
      self.ui.inputSegmentationSelector.currentNode() is not None and\
      self.ui.segmentationBrowserSelector.currentNode() is not None:
      self.ui.inputCollapsibleButton.collapsed = True
    else:
      self.ui.inputCollapsibleButton.collapsed = False

    # If no segmentation node exists then create one so that the user does not have to create one manually

    if not self.ui.editor.segmentationNodeID():
      segmentationNode = slicer.mrmlScene.GetFirstNode(None, "vtkMRMLSegmentationNode")
      if not segmentationNode:
        segmentationNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLSegmentationNode')
      self.ui.editor.setSegmentationNode(segmentationNode)
      if not self.ui.editor.sourceVolumeNodeID():
        masterVolumeNodeID = self.getDefaultMasterVolumeNodeID()
        self.ui.editor.setSourceVolumeNodeID(masterVolumeNodeID)

    layoutManager = slicer.app.layoutManager()
    layoutManager.setLayout(6)

    redController = slicer.app.layoutManager().sliceWidget('Red').sliceController()
    redController.fitSliceToBackground()
  
  def connectKeyboardShortcuts(self):
    self.shortcutS.connect('activated()', self.onSkipButton)
    self.shortcutD.connect('activated()', self.onClearButton)
    self.shortcutC.connect('activated()', self.onCaptureButton)
    self.shortcutA.connect('activated()', self.onOverlayClicked)
  
  def disconnectKeyboardShortcuts(self):
    self.shortcutS.activated.disconnect()
    self.shortcutD.activated.disconnect()
    self.shortcutC.activated.disconnect()
    self.shortcutA.activated.disconnect()

  def exit(self):
    self.ui.editor.setActiveEffect(None)
    self.ui.editor.uninstallKeyboardShortcuts()
    self.ui.editor.removeViewObservations()
    
    self.disconnectKeyboardShortcuts()

  def onSceneStartClose(self, caller, event):
    self.parameterSetNode = None
    self.ui.editor.setSegmentationNode(None)
    self.ui.editor.removeViewObservations()

  def onSceneEndClose(self, caller, event):
    if self.parent.isEntered:
      self.selectParameterNode()
      self.ui.editor.updateWidgetFromMRML()

  def onSceneEndImport(self, caller, event):
    if self.parent.isEntered:
      self.selectParameterNode()
      self.ui.editor.updateWidgetFromMRML()

    self.updateSelections()

  def updateSelections(self):

    browserNodes = slicer.util.getNodesByClass('vtkMRMLSequenceBrowserNode')

    for browser in browserNodes:
      if browser.GetAttribute(self.INPUT_BROWSER) == "True":
        self.ui.inputSequenceBrowserSelector.setCurrentNode(browser)
        slicer.modules.sequences.setToolBarActiveBrowserNode(browser)
        self.ui.inputCollapsibleButton.collapsed = True
        selectedItem = browser.GetAttribute(self.INPUT_LAST_INDEX)
        if selectedItem is not None:
          browser.SetSelectedItemNumber(int(selectedItem))
        skipNumber = browser.GetAttribute(self.INPUT_SKIP_NUMBER)
        if skipNumber is None:
          skipNumber = self.DEFAULT_INPUT_SKIP_NUMBER
        self.ui.skipImagesSpinBox.value = int(skipNumber)
      if browser.GetAttribute(self.OUTPUT_BROWSER) == "True":
        self.ui.segmentationBrowserSelector.setCurrentNode(browser)

    segmentationNodes = slicer.util.getNodesByClass('vtkMRMLSegmentationNode')
    for segmentation in segmentationNodes:
      if segmentation.GetAttribute(self.SEGMENTATION) == "True":
        self.ui.inputSegmentationSelector.setCurrentNode(segmentation)
        self.logic.eraseCurrentSegmentation(segmentation)
        self.ui.editor.setSegmentationNode(segmentation)

    inputImageAttribute = self.parameterSetNode.GetAttribute(self.INPUT_IMAGE_ID)
    if inputImageAttribute is not None:
      inputImageNode = slicer.mrmlScene.GetNodeByID(inputImageAttribute)
      if inputImageNode is not None:
        self.ui.inputVolumeSelector.setCurrentNode(inputImageNode)
        layoutManager = slicer.app.layoutManager()
        sliceLogic = layoutManager.sliceWidget('Red').sliceLogic()
        compositeNode = sliceLogic.GetSliceCompositeNode()
        compositeNode.SetBackgroundVolumeID(inputImageNode.GetID())
        self.ui.editor.setSourceVolumeNode(inputImageNode)

    # Update export folder value if path is found in application settings

    exportFolder = slicer.app.settings().value(self.EXPORT_FOLDER)
    if exportFolder is not None:
      self.ui.outputDirectoryButton.directory = exportFolder



#
# SingleSliceSegmentationLogic
#

class SingleSliceSegmentationLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent=None):
    ScriptedLoadableModuleLogic.__init__(self, parent)

  def exportSlice(self,
                  selectedImage,
                  selectedSegmentation,
                  outputFolder,
                  filenamePrefix,
                  itemNumber):
    if not os.path.exists(outputFolder):
      logging.error("Export folder does not exist {}".format(outputFolder))
      return

    ic = vtk.vtkImageCast()
    ic.SetOutputScalarTypeToUnsignedChar()
    ic.Update()

    png_writer = vtk.vtkPNGWriter()
    labelmapNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLLabelMapVolumeNode')

    slicer.modules.segmentations.logic().ExportVisibleSegmentsToLabelmapNode(
      selectedSegmentation, labelmapNode, selectedImage)
    segmentedImageData = labelmapNode.GetImageData()
    ultrasoundData = selectedImage.GetImageData()

    seg_file_name = filenamePrefix + "_%04d_segmentation" % itemNumber + ".png"
    img_file_name = filenamePrefix + "_%04d_ultrasound" % itemNumber + ".png"
    seg_fullname = os.path.join(outputFolder, seg_file_name)
    img_fullname = os.path.join(outputFolder, img_file_name)

    ic.SetInputData(segmentedImageData)
    ic.Update()
    png_writer.SetInputData(ic.GetOutput())
    png_writer.SetFileName(seg_fullname)
    png_writer.Update()
    png_writer.Write()

    ic.SetInputData(ultrasoundData)
    ic.Update()
    png_writer.SetInputData(ic.GetOutput())
    png_writer.SetFileName(img_fullname)
    png_writer.Update()
    png_writer.Write()

    num_segments = selectedSegmentation.GetSegmentation().GetNumberOfSegments()

    # Assuming we are working with one (or the first) segment
    # Erases the current segmentation
    for i in range(num_segments):
      segmentId = selectedSegmentation.GetSegmentation().GetNthSegmentID(i)
      labelMapRep = selectedSegmentation.GetBinaryLabelmapRepresentation(segmentId)
      labelMapRep.Initialize()
      labelMapRep.Modified()
      selectedSegmentation.Modified()

  def convertSegmentationSequenceToVolumeSequence(self, inputBrowserNode, segmentationNode, ultrasoundNode, value):
    """
    Converts a segmentation sequence to a volume sequence
    """
    print(f"inputBrowserNode: {inputBrowserNode.GetName()}")
    print(f"segmentationNode: {segmentationNode.GetName()}")
    print(f"ultrasoundNode: {ultrasoundNode.GetName()}")
    print(f"value: {value}")

    # Add a new sequence node to the scene and add it to the inputBrowserNode

    volumeSequenceNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSequenceNode", "SegmentationVolumeSequence")
    inputBrowserNode.AddSynchronizedSequenceNode(volumeSequenceNode)

    # Iterate through ever item in the inputBrowserNode and convert the segmentation to a volume

    labelmapVolumeNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLLabelMapVolumeNode')
    scalarVolumeNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLScalarVolumeNode', "SegmentationVolume")
    scalarVolumeNode.CreateDefaultDisplayNodes()

    inputBrowserNode.AddProxyNode(scalarVolumeNode, volumeSequenceNode, False)

    segmentationSequence = inputBrowserNode.GetSequenceNode(segmentationNode)
    if segmentationSequence is None:
      logging.error(f"No segmentation sequence found for segmentation {segmentationNode.GetName()}")
      return

    # Iterate through every item in the inputBrowserNode and convert the segmentation to a volume

    for itemIndex in range(inputBrowserNode.GetNumberOfItems()):
      inputBrowserNode.SetSelectedItemNumber(itemIndex)
      currentSegmentation = segmentationSequence.GetNthDataNode(itemIndex)
      slicer.modules.segmentations.logic().ExportAllSegmentsToLabelmapNode(
        currentSegmentation, labelmapVolumeNode, slicer.vtkSegmentation.EXTENT_REFERENCE_GEOMETRY)
      # slicer.modules.segmentations.logic().ExportVisibleSegmentsToLabelmapNode(
      #   currentSegmentation, labelmapVolumeNode, ultrasoundNode)
      arrayLabelmap = slicer.util.array(labelmapVolumeNode.GetID())
      if arrayLabelmap is not None:
        arrayLabelmap[arrayLabelmap != 0] = 1
        arrayLabelmap *= value
      else:
        arrayLabelmap = slicer.util.array(ultrasoundNode.GetID())
        arrayLabelmap[:, :, :] = 0
      slicer.util.updateVolumeFromArray(scalarVolumeNode, arrayLabelmap)
      indexValue = segmentationSequence.GetNthIndexValue(itemIndex)
      volumeSequenceNode.SetDataNodeAtValue(scalarVolumeNode, indexValue)
      slicer.app.processEvents()



  def exportNumpySlice(self,
                       selectedImage,
                       selectedImageSequence,
                       selectedSegmentation,
                       selectedSegmentationSequence,
                       outputFolder,
                       baseName):

    if not os.path.exists(outputFolder):
      logging.error("Export folder does not exist {}".format(outputFolder))
      return

    labelmapNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLLabelMapVolumeNode')

    seg_file_name = baseName + "_segmentation"
    img_file_name = baseName + "_ultrasound"
    ind_file_name = baseName + "_indices"
    seg_fullname = os.path.join(outputFolder, seg_file_name)
    img_fullname = os.path.join(outputFolder, img_file_name)
    ind_fullname = os.path.join(outputFolder, ind_file_name)

    # Get whole image volume (each frame in the original recording)
    num_items = selectedImageSequence.GetNumberOfItems()
    selectedImageSequence.SelectFirstItem()
    img_numpy_size = slicer.util.arrayFromVolume(selectedImage).shape
    img_seq_numpy = np.zeros((num_items, img_numpy_size[1], img_numpy_size[2], 1), dtype=np.uint8)

    for i in range(num_items):

      img_numpy = slicer.util.arrayFromVolume(selectedImage)
      resize_img_numpy = np.expand_dims(img_numpy, axis=3)

      img_seq_numpy[i, ...] = resize_img_numpy

      selectedImageSequence.SelectNextItem()
      slicer.app.processEvents()

    np.save(img_fullname, img_seq_numpy)
      
    # Get each segmentation at the right spot in volume the same size as the images, and store all original indices
    num_items = selectedSegmentationSequence.GetNumberOfItems()
    selectedSegmentationSequence.SelectFirstItem()

    seg_seq_numpy = np.zeros(img_seq_numpy.shape, dtype=np.uint8)

    originalIndices = np.array([], dtype=np.uint8)
    
    for i in range(num_items):

      slicer.modules.segmentations.logic().ExportVisibleSegmentsToLabelmapNode(selectedSegmentation,
                                                                               labelmapNode, selectedImage)
      seg_numpy = slicer.util.arrayFromVolume(labelmapNode)
      resize_seg_numpy = np.expand_dims(seg_numpy, axis=3)
      segmentationIndex = int(selectedSegmentation.GetAttribute(SingleSliceSegmentationWidget.ORIGINAL_IMAGE_INDEX))
      originalIndices = np.append(originalIndices, segmentationIndex)
      seg_seq_numpy[segmentationIndex, ...] = resize_seg_numpy

      selectedSegmentationSequence.SelectNextItem()
      slicer.app.processEvents()

    np.save(seg_fullname, seg_seq_numpy)
    np.save(ind_fullname, originalIndices)

  def exportPngSequence(self,
                        selectedImage,
                        selectedImageSequence,
                        selectedSegmentation,
                        selectedSegmentationSequence,
                        outputFolder,
                        baseName):
    if not os.path.exists(outputFolder):
      logging.error("Export folder does not exist {}".format(outputFolder))
      return

    imageCast = vtk.vtkImageCast()
    imageCast.SetOutputScalarTypeToUnsignedChar()
    imageCast.Update()

    pngWriter = vtk.vtkPNGWriter()
    labelmapNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLLabelMapVolumeNode')

    num_items = selectedSegmentationSequence.GetNumberOfItems()
    selectedSegmentationSequence.SelectFirstItem()
    for i in range(num_items):
      originalIndex = selectedSegmentation.GetAttribute(SingleSliceSegmentationWidget.ORIGINAL_IMAGE_INDEX)
      if originalIndex == None:
        logging.warning("Input image index attribute not found in segmentation. Input sequence will not be used.")
      else:
        try:
          selectedImageSequence.SetSelectedItemNumber(int(originalIndex))
        except:
          logging.error(f"Original image not found for segmentation {i} - skipping")
          continue

      slicer.modules.sequences.logic().UpdateAllProxyNodes()

      slicer.modules.segmentations.logic().ExportVisibleSegmentsToLabelmapNode(selectedSegmentation,
                                                                               labelmapNode,
                                                                               selectedImage)
      segmentationArray = slicer.util.arrayFromVolume(labelmapNode)
      segmentationArray *= 255
      slicer.util.updateVolumeFromArray(labelmapNode, segmentationArray)
      segmentedImageData = labelmapNode.GetImageData()
      ultrasoundData = selectedImage.GetImageData()

      segmentationFileName = baseName + "_%04d_segmentation" % i + ".png"
      ultrasoundFileName = baseName + "_%04d_ultrasound" % i + ".png"
      segmentationFullname = os.path.join(outputFolder, segmentationFileName)
      ultrasoundFullname = os.path.join(outputFolder, ultrasoundFileName)

      imageCast.SetInputData(segmentedImageData)
      imageCast.Update()
      pngWriter.SetInputData(imageCast.GetOutput())
      pngWriter.SetFileName(segmentationFullname)
      pngWriter.Update()
      pngWriter.Write()

      imageCast.SetInputData(ultrasoundData)
      imageCast.Update()
      pngWriter.SetInputData(imageCast.GetOutput())
      pngWriter.SetFileName(ultrasoundFullname)
      pngWriter.Update()
      pngWriter.Write()

      selectedSegmentationSequence.SelectNextItem()
      slicer.modules.sequences.logic().UpdateAllProxyNodes()


  def exportTransformToWorldSequence(self,
                                     selectedImage,
                                     selectedImageSequence,
                                     selectedSegmentation,
                                     selectedSegmentationSequence,
                                     outputFolder,
                                     baseName):
    if not os.path.exists(outputFolder):
      logging.error("Export folder does not exist {}".format(outputFolder))
      return

    # Find out if selectedImage is transformed by an transform node in the scene
    # If so, we will use that transform to get the transform to world for each frame

    imageTransformID = selectedImage.GetTransformNodeID()
    if imageTransformID is None:
      logging.warning("Image is not transformed; no transform to world will be exported.")
      return
    else:
      imageTransform = slicer.mrmlScene.GetNodeByID(imageTransformID)

    num_items = selectedImageSequence.GetNumberOfItems()
    selectedImageSequence.SelectFirstItem()

    transforms_seq_numpy = np.zeros((num_items, 4, 4))

    for i in range(num_items):

      # Get landmarking scan transform, get TransformToWorld
      transformToWorld = vtk.vtkMatrix4x4()
      imageTransform.GetMatrixTransformToWorld(transformToWorld)
      transformToWorld_numpy = slicer.util.arrayFromVTKMatrix(transformToWorld)
      
      transforms_seq_numpy[i, ...] = transformToWorld_numpy

      selectedImageSequence.SelectNextItem()
      slicer.app.processEvents()
    
    # Save stacked transforms as output numpy array.
    transformFileName = baseName + "_transform.npy"
    transformFullname = os.path.join(outputFolder, transformFileName)
    np.save(transformFullname, transforms_seq_numpy)


  def captureSlice(self, segmentationSequenceBrowser, selectedSegmentation, inputImage):
    """
    Saves current segmentation in the selected segmentation sequence browser.
    If the current input image index is already associated with a saved segmentation, that saved segmentation will be replaced
    to avoid saving two different segmentations for the same input image.
    :param segmentationSequenceBrowser: Output sequence browser for segmentations
    :param selectedSegmentation: Output segmentation node, proxy node of one of the sequences in segmentationSequenceBrowser
    :param inputImage: Input volume node, proxy node of one of the sequences in segmentationSequenceBrowser
    """

    # Find sequences in selected browser associated with then inputImage and selectedSegmentation as proxy nodes
    
    inputImageSequenceNode = segmentationSequenceBrowser.GetSequenceNode(inputImage)
    if inputImageSequenceNode is None:
      logging.error("Sequence not found for input image: {}".format(inputImage.GetName()))
      return
    
    segmentationSequenceNode = segmentationSequenceBrowser.GetSequenceNode(selectedSegmentation)
    if segmentationSequenceNode is None:
      logging.error("Sequence not found for segmentation: {}".format(selectedSegmentation.GetName()))
      return
    
    # Check all nodes saved in the segmentation sequence if any of them has the same input image index attribute

    originalIndex = selectedSegmentation.GetAttribute(SingleSliceSegmentationWidget.ORIGINAL_IMAGE_INDEX)
    recordedOriginalIndex = None

    numSegmentationNodes = segmentationSequenceNode.GetNumberOfDataNodes()
    for i in range(numSegmentationNodes):
      segmentationNode = segmentationSequenceNode.GetNthDataNode(i)
      savedIndex = segmentationNode.GetAttribute(SingleSliceSegmentationWidget.ORIGINAL_IMAGE_INDEX)
      if originalIndex == savedIndex:
        recordedOriginalIndex = i
        break
    
    # If this image has been saved previously, overwrite instead of add new
    
    try:
      recordedOriginalIndex = int(recordedOriginalIndex)
    except:
      recordedOriginalIndex = None
    
    if recordedOriginalIndex is None:
      segmentationSequenceBrowser.SaveProxyNodesState()
    else:
      recordedIndexValue = inputImageSequenceNode.GetNthIndexValue(recordedOriginalIndex)
      segmentationSequenceNode.SetDataNodeAtValue(selectedSegmentation, recordedIndexValue)

  def eraseCurrentSegmentation(self, selectedSegmentation):
    num_segments = selectedSegmentation.GetSegmentation().GetNumberOfSegments()
    for i in range(num_segments):
      segmentId = selectedSegmentation.GetSegmentation().GetNthSegmentID(i)

      import vtkSegmentationCorePython as vtkSegmentationCore
      try:
        labelMapRep = selectedSegmentation.GetBinaryLabelmapRepresentation(segmentId)
      except:
        labelMapRep = selectedSegmentation.GetBinaryLabelmapInternalRepresentation(segmentId)
      slicer.vtkOrientedImageDataResample.FillImage(labelMapRep, 0, labelMapRep.GetExtent())
      slicer.vtkSlicerSegmentationsModuleLogic.SetBinaryLabelmapToSegment(
        labelMapRep, selectedSegmentation, segmentId, slicer.vtkSlicerSegmentationsModuleLogic.MODE_REPLACE)
    if num_segments > 1:
      selectedSegmentation.Modified()

class SingleSliceSegmentationTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """


  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear(0)


  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_SingleSliceSegmentation1()


  def test_SingleSliceSegmentation1(self):
    pass
