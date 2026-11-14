-- Title screens of the login screen. tools/patch_lua_title.py places this file in UI_Login.lua (gcg2#33).
-- The same module is release/client/title_screens.lua of GirlCafeGun-Remake; keep the two alike.
--
-- The login prefab draws two titles. The hall is the stock branch of Load2DBG. The scene is the state
-- the prefab loads in: a background picture on PnlBGEffect/Image3, the 4-girl animation on "Spine"
-- (component ShowConcertModel: girl and suit numbers) and particles in PnlBGEffect/eftParent4.
-- The scene can show other art that the client data holds: another picture and another suit of the
-- animation. This file ships no asset. A title is shown only when its picture and its animation load
-- in this client. The hall and the prefab's own scene need nothing new and are always possible.
local P = {}
P.cfg = {
  -- weight: share of starts among the titles that this client can draw; 0 removes a title.
  -- texture: path below Textures/, as for Game.LuaUtils.LoadTexture2D. ratio: width / height of it.
  -- suit: SuitId of ShowConcertModel (2D Animation/girl1002_2da<suit>). animation: name in that model.
  -- particles: the cherry petals of eftParent4 belong to the sky title only.
  -- scale: Scale of ShowConcertModel. position: anchoredPosition of "Spine". logo: anchoredPosition of
  -- PnlBG/ImgLogo. Each is optional; without it the value of the prefab stays. Set by eye on a 2340 x 1080
  -- phone: at the prefab's scale suit 3 is far too large, and the stock logo place covers a face.
  titles = {
    { name = 'hall', weight = 1, hall = true },
    { name = 'sky', weight = 1, texture = 'BG/bg_login04.png', ratio = 4 / 3, suit = 2,
      animation = 'Mgirl01_stand', particles = true },
    { name = 'snow', weight = 1, texture = 'BG/bg_login03.png', ratio = 4 / 3, suit = 1,
      animation = 'idle', position = { -50.5, -42.5 }, logo = { 300, 212 } },
    { name = 'shards', weight = 1, texture = 'BG/bg_login05.png', ratio = 2, suit = 3,
      animation = 'Mgirl09_stand', scale = 83, position = { 0, 0 }, logo = { 300, 212 } },
  },
}
local IMAGE, PARTICLES, SPINE = 'PnlBGEffect/Image3', 'PnlBGEffect/eftParent4', 'Spine'

local function log(text) print('[title] ' .. text) end

-- A number from 0 to 1. No stock script uses UnityEngine.Random, and math.random is not seeded
-- before login, so the clock is the second source.
local function roll()
  local ok, value = pcall(function() return U3D.Random.value end)
  if ok and type(value) == 'number' then return value end
  return (os.time() % 100) / 100
end

-- False for nil and for a Unity object that was destroyed.
local function alive(object)
  if object == nil then return false end
  local ok, gone = pcall(function() return object:Equals(nil) end)
  return not (ok and gone)
end

-- The scene parts of this prefab, and the state they load in.
local function parts(self)
  local s = {}
  s.image = self:GetComponent('RawImage', IMAGE)
  s.particles = self:FindObject(PARTICLES)
  s.spine = self:FindObject(SPINE)
  s.model = s.spine and s.spine:GetComponent('ShowConcertModel')
  s.texture = s.image and s.image.texture
  s.suit = s.model and s.model.SuitId
  s.active = s.spine and s.spine.activeSelf
  s.scale = s.model and s.model.Scale
  s.rect = s.spine and s.spine:GetComponent('RectTransform')
  s.position = s.rect and s.rect.anchoredPosition
  return s
end

-- A title that names the picture the prefab already shows is the prefab's own scene.
local function own(s, title)
  return alive(s.texture) and title.texture ~= nil
    and s.texture.name == title.texture:match('([^/]+)%.%w+$')
end

local function shown(model)
  if alive(model.spine) then return model.spine end
  if alive(model.live2d) then return model.live2d end
end

-- Loads a suit of the animation. True only when a new model object stands there afterwards:
-- a model left over from the suit before is not this suit.
-- Size and place of the animation: those of a title, or without a title those of the prefab.
local function place(s, title)
  s.model.Scale = title and title.scale or s.scale
  if s.rect and s.position then
    local at = title and title.position
    s.rect.anchoredPosition = at and U3D.Vector2(at[1], at[2]) or s.position
  end
end

local function animate(s, title)
  local before = shown(s.model)
  s.model.SuitId = title.suit
  place(s, title)
  s.spine:SetActive(true)
  s.model:Load()
  local after = shown(s.model)
  if not after or after == before then return false end
  if title.animation then pcall(s.model.Play, s.model, title.animation) end
  return true
end

local function restore(s)
  s.model.SuitId = s.suit
  place(s, nil)
  pcall(s.model.Load, s.model)
  s.spine:SetActive(s.active)
end

local function ownScene(s)
  if s.spine then s.spine:SetActive(true) end
end

-- Shows a scene title with other art. False, with the prefab's state back, when a part does not load.
local function scene(self, s, title)
  if not s.image or not s.model then return false, 'the prefab has no ' .. IMAGE .. ' or no model on ' .. SPINE end
  local ok, texture = pcall(function() return Game.LuaUtils.LoadTexture2D(title.texture) end)
  if not ok or not alive(texture) then return false, 'no texture ' .. title.texture end
  local loaded, done = pcall(animate, s, title)
  if not loaded or not done then
    restore(s)
    return false, 'no animation suit ' .. tostring(title.suit)
  end
  -- The stock ModifyBackground makes this call for the stock picture; the ratio fits the frame to it.
  pcall(function() Game.Utils.SetAndModifyBackground(self.pRoot, IMAGE, title.texture, title.ratio) end)
  if s.image.texture ~= texture then s.image.texture = texture end
  pcall(self.BackgroundAdapter, self)
  if s.particles then s.particles:SetActive(title.particles == true) end
  if title.logo and self.ImgLogoRect then
    self.ImgLogoRect.anchoredPosition = U3D.Vector2(title.logo[1], title.logo[2])
  end
  return true
end

-- Takes one title out of the list, by weight.
local function pick(list)
  local total = 0
  for _, title in ipairs(list) do total = total + title.weight end
  local at = roll() * total
  for i, title in ipairs(list) do
    at = at - title.weight
    if at < 0 then return table.remove(list, i) end
  end
  return table.remove(list)
end

-- Shows one title. True when it is the hall: Load2DBG then runs its stock hall branch.
function P.Show(self)
  local s, list, named = parts(self), {}, false
  for _, title in ipairs(P.cfg.titles) do
    if type(title.weight) == 'number' and title.weight > 0 then list[#list + 1] = title end
    named = named or own(s, title)
  end
  -- When no title of the table is the picture of this prefab, its scene still takes part.
  if not named and #list > 0 then list[#list + 1] = { name = 'scene of the prefab', weight = 1, own = true } end
  while #list > 0 do
    local title = pick(list)
    if title.hall then
      if s.spine then s.spine:SetActive(false) end
      log(title.name)
      return true
    elseif title.own or own(s, title) then
      ownScene(s)
      log(title.name)
      return false
    else
      local done, why = scene(self, s, title)
      if done then log(title.name) return false end
      log(title.name .. ' left out: ' .. why)
    end
  end
  ownScene(s)
  log('scene of the prefab')
  return false
end

-- Load2DBG asks this in place of its language test. An error gives the stock answer back.
function P.Choose(self)
  local ok, hall = pcall(P.Show, self)
  if ok then return hall end
  log('failed, stock title: ' .. tostring(hall))
  return self:IsUS()
end

TitleScreens = P
