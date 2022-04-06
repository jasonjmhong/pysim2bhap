from time import sleep
#from importlib import reload 
#import better_haptic_player as player
import haptic_player
import os, sys
import time
import math
import traceback
import simconnect
import logging as log


varList = ["GENERAL ENG PCT MAX RPM:1", "AIRSPEED MACH", "BARBER POLE MACH",
           "ACCELERATION BODY X", "ACCELERATION BODY Y", "ACCELERATION BODY Z", 
           "TRAILING EDGE FLAPS LEFT PERCENT", "GEAR LEFT POSITION", "G FORCE",
           "SIM ON GROUND", "INCIDENCE ALPHA", "INCIDENCE BETA"]

class Sim():
  def __init__(self, port = 500, ipAddr = '127.0.0.1'):
    self.speedThreshold = 0.75
    self.rpmThreshold = 0.95
    self.gfeThreshold = 2.6
    self.fullArms = False
    self.accelThreshold = 0.75
    self.maxSpeed = 700.0
    self.maxRpm = 3000.0
    self.aoaThreshold = 0.75
    self.maxAoA = 20
    self.forceMultiplier = 1.0
    self.durationMultiplier = 1.0  
    self.player = haptic_player.HapticPlayer()
    
  def play(self, name, intensity, altname, duration = 1):
    self.player.submit_registered_with_option(name, altname,
       scale_option={"intensity": intensity*self.forceMultiplier, "duration": duration*self.durationMultiplier},
       rotation_option={"offsetAngleX": 0, "offsetY": 0})

  def start(self):
    self.cycle = 0
    self.ValueDict = {}
    self.sc = None
    self.lastAcel = None
    self.lastFlapPos = None
    self.lastGearPos = None
    errCode = 'valid'
    try:
      #player.initialize()
      
      # tact file can be exported from bhaptics designer
      try:
        self.player.register("msfs_vvne", "msfs_vvne.tact")
        self.player.register("msfs_vrpm", "msfs_vrpm.tact")
        self.player.register("msfs_vgfe", "msfs_vgfe.tact")
        self.player.register("msfs_arpm", "msfs_arpm.tact")
        self.player.register("msfs_vace", "msfs_vace.tact")
        self.player.register("msfs_vfla", "msfs_vfla.tact")
        self.player.register("msfs_vaoa", "msfs_vaoa.tact")
      except:
        msg = 'Error conecting. Is bHaptics player app running?\n'
        log.exception(msg)
        return (msg, 'error')
      
      # open a connection to the SDK
      # or use as a context via `with SimConnect() as sc: ... `
      self.sc = simconnect.SimConnect(poll_interval_seconds=0.042)
      
      
      # subscribing to one or more variables is much more efficient,
      # with the SDK sending updated values up to once per simulator frame.
      # the variables are tracked in `datadef.simdata`
      # which is a dictionary that tracks the last modified time
      # of each variable.  changes can also trigger an optional callback function
      self.datadef = self.sc.subscribe_simdata(
          varList,
          # request an update every ten rendered frames
          period=simconnect.PERIOD_VISUAL_FRAME,
          interval=1,
      )
      # track the most recent data update
      #self.latest = self.datadef.simdata.latest()
      #print("Inferred variable units", self.datadef.get_units())
      msg = "msfsBHap started\n"
    except Exception as excp:
      errCode = 'error'
      msg = (str(excp)+'\n'+traceback.format_exc())
    return (msg, errCode)

  def runCycle(self):
    self.cycle += 1
    errCode = 'none'
    msg = ''
    try:
   
      # pump the SDK event queue to deal with any recent messages
      while self.sc.receive():
          pass
          
      #print (self.datadef.simdata)
   
      # show data that's been changed since the last update
      #print(f"Updated data {self.datadef.simdata.changedsince(self.latest)}")
      
      for varName in self.datadef.simdata:
        self.ValueDict[varName] = self.datadef.simdata[varName]

      impactForce = 0
      acelX = self.datadef.simdata["ACCELERATION BODY X"]
      acelZ = self.datadef.simdata["ACCELERATION BODY Z"]
      acel2 = math.sqrt(acelX*acelX+acelZ*acelZ)
      acelY = self.datadef.simdata["ACCELERATION BODY Y"]
      acel = math.sqrt(acelY*acelY+acel2*acel2) * 0.3048
      if (self.lastAcel is not None):
        acelChange = abs(acel - self.lastAcel)
        impactForce = (acelChange - self.accelThreshold) / 20.0
      self.lastAcel = acel
      
      if impactForce > 0.01:
        msg += "Acc {} {}\n".format(impactForce, acelChange)
        self.play("msfs_arpm", impactForce, "alt1") 
        self.play("msfs_vace", impactForce, "alt2") 

      if self.cycle % 3 != 0:
        return (msg, errCode)
   
      #self.latest = self.datadef.simdata.latest()
   
      onGround = self.datadef.simdata["SIM ON GROUND"]
      aoa = self.datadef.simdata["INCIDENCE ALPHA"] * 57.2958
      aoaVibration = ((aoa/self.maxAoA) - self.aoaThreshold) / (1 - self.aoaThreshold)
      #print ("{} {} {}".format(onGround, aoa, aoaVibration))
      if (not onGround) and (aoaVibration > 0.01):
        msg += "AoA {} {}\n".format(aoaVibration, aoa)
        if self.fullArms:
          self.play("msfs_arpm", aoaVibration, "alt3")
        self.play("msfs_vaoa", aoaVibration, "alt4")
        
      speedVibration = (self.datadef.simdata["AIRSPEED MACH"]/self.datadef.simdata["BARBER POLE MACH"]) - self.speedThreshold
      if (speedVibration > 0):
        speedVibration = speedVibration * speedVibration * 4
        if (speedVibration > 0.01):
          msg += "SPEED {} {}\n".format(speedVibration, self.datadef.simdata["AIRSPEED MACH"])
          if self.fullArms:
            self.play("msfs_arpm", speedVibration, "alt5")
          self.play("msfs_vvne", speedVibration, "alt6")
                      
      engineVibration = self.datadef.simdata["GENERAL ENG PCT MAX RPM:1"]/100 - self.rpmThreshold
      if (engineVibration > 0):
        engineVibration = engineVibration * engineVibration * 4
        if (engineVibration > 0.01):
          msg += "RPM {} {}\n".format(engineVibration, self.datadef.simdata["GENERAL ENG PCT MAX RPM:1"])
          self.play("msfs_arpm", engineVibration, "alt7")
          self.play("msfs_vrpm", engineVibration, "alt8")
   
      gForceVibration = (self.datadef.simdata["G FORCE"] - self.gfeThreshold) / 8
      if (gForceVibration > 0):
        gForceVibration = gForceVibration * gForceVibration * 4
        if (gForceVibration > 0.01):
          msg += "GFe {} {}\n".format(gForceVibration, self.datadef.simdata["G FORCE"])
          if self.fullArms:
            self.play("msfs_arpm", gForceVibration, "alt9")
          self.play("msfs_vgfe", gForceVibration, "alt10")

      flapsChange = 0
      flapPos = self.datadef.simdata["TRAILING EDGE FLAPS LEFT PERCENT"]
      if (self.lastFlapPos is not None):
        flapsChange = abs(flapPos - self.lastFlapPos)
      self.lastFlapPos = flapPos

      gearChange  = 0
      gearPos = self.datadef.simdata["GEAR LEFT POSITION"]
      if (self.lastGearPos is not None):
        gearChange = abs(gearPos - self.lastGearPos)
      self.lastGearPos = gearPos
      
      if (flapsChange > 0.005) or (gearChange > 0.005):
        msg += "Flp {} {} {} {}\n".format(flapsChange, flapPos, gearChange, gearPos)
        if self.fullArms:
          self.play("msfs_arpm", 0.1, "alt11") 
        self.play("msfs_vfla", 0.5, "alt12") 

    except Exception as excp:
      errCode = 'error'
      msg = (str(excp)+'\n'+traceback.format_exc())

    return (msg, errCode)
  def stop(self):
    #player.destroy()
    if self.sc:
      self.sc.Close()
      self.sc = None
      del self.sc
      self.datadef = None
      #del sys.modules["simconnect"]
    return ("msfsBHap stopped\n", "valid")

if __name__ == "__main__": 

  sim = Sim()
  print(sim.start())
  sleep(3)
  while True:
    print(sim.runCycle())
    sleep(0.125)
  sim.stop()
