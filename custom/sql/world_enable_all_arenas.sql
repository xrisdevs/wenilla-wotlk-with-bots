-- Enable Dalaran Sewers (10) and Ring of Valor (11); TDB ships them disabled.
DELETE FROM disables WHERE sourceType=3 AND entry IN (10,11);
